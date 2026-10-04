"""
Deterministic dialogue state: what does the customer's latest message MEAN in this conversation?

The model is good at language and bad at bookkeeping. Prod chat 2026-10-04 showed the same
failures again and again:
  * "Yes" / "hunxa" / "ah hunxa" after "Herna jaana chahanuhunchha?" -> the agent asked the SAME
    question again instead of doing it (three times in one chat).
  * "Yes" after "Shall I ask the team for photos?" -> asked again; a later "request your team"
    -> "Request sent" with no request recorded anywhere.
  * "Can you give me more photos" -> "no more photos" from memory of an earlier turn, while staff
    had uploaded more in the meantime; only "search the database again" made it call the tool.

So before the model runs we resolve the turn in code (an affirmation answers the agent's last
question; a photo request needs the photo tool; "check again" needs a fresh tool call) and tell
the model in a binding TURN BRIEF. After it drafts, `problems()` checks the draft against the brief
and the tools it actually called; violations go through the normal corrective retry.
"""
import difflib
import re
from dataclasses import dataclass, field
from typing import Dict, List

from . import actions

_SENTENCE_END = re.compile(r'(?<=[.!?।？])\s+|\n+')

AFFIRM_EXTRA = {'go', 'please', 'sure', 'definitely', 'absolutely', 'ok', 'okay', 'k', 'kk', 'yess', 'yes',
                'yea', 'ya', 'yah', 'ha', 'haa', 'hus', 'huss', 'hunchha', 'hunxa', 'huncha', 'la', 'thikai',
                'thik', 'thikchha', 'garnus', 'gara', 'garnu', 'pathaunu', 'pathaunus', 'gardinu', 'gardeu',
                'request', 'ask', 'do', 'it', 'that', 'chahiyo', 'chaiyo', 'chahinchha', 'chainchha',
                'हुन्छ', 'हस्', 'ठिक', 'हो', 'हजुर', 'गर्नुस्', 'पठाउनुस्', '好', '可以', '是'}
_NEG = re.compile(r"\b(no|nope|not|don'?t|dont|hoina|haina|pardaina|chaina|chhaina|nagarnu\w*|wait)\b|"
                  r"होइन|पर्दैन|छैन|不", re.I)

PHOTO_RE = re.compile(r'\b(photos?|pics?|pictures?|images?|tasbir|foto|fotos)\b|फोटो|तस्बिर|照片|相片', re.I)
RETRY_RE = re.compile(r'\b(again|feri|pheri|re-?check|refresh)\b|फेरि|再'
                      r'|\b(check|search|look|hernu|herna|khojnu|khoja)\b[^.?!]{0,40}\b(database|storage|system|record)\b'
                      r'|\b(database|storage|system|record)\b[^.?!]{0,40}\b(check|search|look|hernu|herna|khojnu)\b',
                      re.I)

OFFER_KINDS = {
    'team_request': re.compile(r'\b(team|staff|agent|office)\b|magera|sodhera|टिम', re.I),
    'photos': re.compile(r'\b(photos?|pictures?|images?)\b|फोटो', re.I),
    'viewing': re.compile(r'\b(view(ing)?|visit|herna|hernu|see it|schedule|tour)\b|हेर्न|भ्यूइङ', re.I),
    'details': re.compile(r'\b(details?|bibaran|information|more info)\b|विवरण', re.I),
    'more_options': re.compile(r'\b(more options|other options|aru option|similar|nearby)\b', re.I),
}
NEXT_STEP = {
    'team_request': "call request_team_followup NOW with exactly what they want from the team (and the listing "
                    "reference), then tell them it has been passed on. Do not ask again.",
    'photos': "call send_property_photos NOW for the listing in context.",
    'viewing': "move the booking forward: if they already named a day, call get_viewing_slots for it and offer the "
               "free times; otherwise ask ONE question: which day and roughly what time suits them. Never repeat "
               "'do you want to view it?' and never pick a time for them.",
    'details': "call get_property_details NOW for the listing in context and give the key facts.",
    'more_options': "call search_properties NOW (same criteria, exclude what was shown) and give the options.",
}

TEAM_TOOLS = {'request_team_followup', 'escalate_to_human', 'save_lead'}
# A statement (not a question) that something was / will be passed to the team.
TEAM_CLAIM_RE = re.compile(
    r"\b(passed|forwarded|sent|relayed|noted)\b[^.?!\n]{0,40}\b(team|staff|agent)s?\b"
    r"|\b(team|staff)\b[^.?!\n]{0,30}\b(will|to)\b[^.?!\n]{0,20}\b(send|share|upload|call|contact|get back|check)"
    r"|\bI('ll| will| have|'ve)\b[^.?!\n]{0,15}\b(ask|tell|inform|notify|request|check with)\b[^.?!\n]{0,25}\b(team|staff)"
    r"|\brequest(ed)? (has been |was )?(sent|made|passed)"
    r"|team (sanga|lai)[^.?!\n]{0,40}(pathaidinchhu|pathaidinchu|garidinchhu|garidinchu|bhanidinchhu|bhanidinchu|"
    r"magera|sodhera|pathaieko|bhaneko|pathayeko|khabar)"
    r"|टिम(सँग|लाई)[^।?!\n]{0,40}(पठाइदिन्छु|गरिदिन्छु|भनिदिन्छु|पठाएको|भनेको)", re.I)
# An offer, not a promise: "Chahinchha bhane ma team sanga magidinchhu", "If you like, I'll ask the team".
CONDITIONAL_RE = re.compile(r"\b(bhane|vane|bhaye|vaye|if|would you|shall i|do you want|want me|can i|could i)\b"
                            r"|भने|भए", re.I)
PHOTO_CLAIM_RE = re.compile(
    r"\b(no|not|any|only|more|sent|attached|uploaded|pathai\w*|attach)\b[^.?!\n]{0,40}\b(photos?|pictures?|images?)\b"
    r"|\b(photos?|pictures?|images?)\b[^.?!\n]{0,40}\b(sent|attached|uploaded|available|upload|chhaina|chaina|"
    r"pathai\w*|chha|xa)\b|फोटो", re.I)


@dataclass
class TurnBrief:
    affirmed: bool = False
    offer: str = ''                      # what their yes answers ('' = no single clear offer)
    offers: List[str] = field(default_factory=list)
    last_question: str = ''
    wants_photos: bool = False
    retry: bool = False
    pending_preview: bool = False
    quoted: dict = field(default_factory=dict)
    lines: List[str] = field(default_factory=list)

    def text(self) -> str:
        return "\n".join(f"- {line}" for line in self.lines) or "- (nothing special: follow INTENT)"


def is_affirmation(text: str) -> bool:
    """'yes', 'hunxa', 'ah hunxa', 'Yes go ahead', 'Yes request your team', 'हुन्छ' - short and positive."""
    t = (text or '').strip().lower()
    if not t or len(t) > 60 or '?' in t or _NEG.search(t):
        return False
    words = re.findall(r"[\wऀ-ॿ一-鿿]+", t)
    if not words or len(words) > 8:
        return False
    if actions.is_plain_confirmation(t):
        return True
    starts_yes = words[0] in actions._AFFIRM | {'ah', 'aa', 'haa', 'ha', 'ok', 'okay', 'yes', 'yeah', 'sure'}
    return starts_yes and sum(w in (actions._AFFIRM | AFFIRM_EXTRA) for w in words) >= max(1, len(words) // 2)


def last_question(assistant_text: str) -> str:
    sentences = [s.strip() for s in _SENTENCE_END.split(assistant_text or '') if s.strip()]
    asks = [s for s in sentences if s.endswith(('?', '？'))]
    return asks[-1] if asks else ''


def offer_kinds(question: str) -> List[str]:
    return [k for k, rx in OFFER_KINDS.items() if rx.search(question or '')]


def analyse(current: str, history: List[Dict[str, str]], pending_preview: bool) -> TurnBrief:
    brief = TurnBrief(pending_preview=pending_preview)
    prev_ai = next((m['content'] for m in reversed(history) if m['role'] == 'assistant'), '')
    brief.last_question = last_question(prev_ai)
    brief.offers = offer_kinds(brief.last_question)
    brief.wants_photos = bool(PHOTO_RE.search(current or ''))
    brief.retry = bool(RETRY_RE.search(current or ''))
    brief.affirmed = is_affirmation(current)

    if brief.affirmed and pending_preview:
        brief.lines.append("The customer's message is a YES to the PENDING DECISION: call confirm_pending_action.")
    elif brief.affirmed and brief.last_question:
        offers = brief.offers
        # "photos -> ask the team for photos?" is ONE offer: a team request.
        if 'team_request' in offers:
            offers = ['team_request']
        if len(offers) == 1:
            brief.offer = offers[0]
            brief.lines.append(f"The customer's message \"{current.strip()}\" is a YES to your last question "
                               f"\"{brief.last_question}\". Do it now: {NEXT_STEP[brief.offer]}")
        elif offers:
            brief.lines.append(f"The customer said yes to a question with several options (\"{brief.last_question}\"). "
                               "If one option is clearly meant, do it; otherwise ask which ONE they want, in one "
                               "short question. Never invent a date or time for them.")
        else:
            brief.lines.append(f"The customer's message is a YES to your last question \"{brief.last_question}\". "
                               "Carry it out with the right tool; never ask the same question again.")
    if brief.wants_photos:
        brief.lines.append("They want photos: call send_property_photos THIS turn (staff upload photos at any time, "
                           "so an earlier turn's result is outdated). If it returns NO_PHOTOS, say so and offer to "
                           "ask the team (request_team_followup after they agree).")
    if brief.retry:
        brief.lines.append("They ask you to check again: call the relevant tool again THIS turn; never answer from "
                           "an earlier result.")
    return brief


def problems(reply: str, brief: TurnBrief, tools_called: List[str], tools_ok: List[str]) -> List[str]:
    """Violations of the TURN BRIEF / promise rules, phrased as fixes for the corrective retry."""
    out = []
    called = set(tools_called)
    statements = [s for s in _SENTENCE_END.split(reply or '') if s.strip() and '?' not in s and '？' not in s]

    promises = [s for s in statements if TEAM_CLAIM_RE.search(s) and not CONDITIONAL_RE.search(s)]
    if promises and not (TEAM_TOOLS & set(tools_ok)):
        out.append("TEAM_PROMISE_WITHOUT_RECORD: you say something was or will be passed to the team, but no "
                   "request was recorded. Call request_team_followup (what they need + listing reference) and "
                   "only then say it was passed on; or offer it as a question instead.")
    # "I passed your request for photos to the team" is a team sentence, not a claim about photos.
    photo_claim = any(PHOTO_CLAIM_RE.search(s) and not TEAM_CLAIM_RE.search(s) for s in statements)
    # A details answer may mention photos from get_property_details (it returns the photo list);
    # an explicit request for photos always needs the send tool.
    checked = 'send_property_photos' in called or (not brief.wants_photos and 'get_property_details' in called)
    if (brief.wants_photos or photo_claim) and not checked \
            and (photo_claim or not reply.strip().endswith('?')):
        out.append("PHOTOS_NOT_CHECKED: you talk about photos without calling send_property_photos this turn. "
                   "Call it now (photos may have been uploaded since) and report its real result.")
    if brief.retry and not called:
        out.append("RECHECK_IGNORED: the customer asked you to check again but you called no tool. Call the "
                   "relevant tool now.")
    if brief.affirmed and brief.last_question and not brief.pending_preview:
        again = last_question(reply)
        if again and difflib.SequenceMatcher(None, again.lower(), brief.last_question.lower()).ratio() > 0.75:
            out.append(f"REPEATED_QUESTION: the customer already answered YES to \"{brief.last_question}\". "
                       "Do not ask it again; carry it out (see TURN BRIEF).")
    return out
