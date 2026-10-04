"""
Respect (register) gate: customers are always addressed in the honorific register.

Regression for the 2026-10-03 WhatsApp chat: "Herna jaana chahanuhunchha?" (good) was followed
by "Aru sodhna cha?" (curt, low register) twice in the same conversation.
"""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from apps.accounts.models import Location, Organization
from apps.ai_engine.agent import tone
from apps.ai_engine.agent.language import NEPALI_DEVANAGARI, NEPALI_ROMAN, detect_reply_style
from apps.ai_engine.services import AIService
from apps.messaging.models import Channel, Conversation, Message, MessageSender
from apps.realestate.models import PropertyListing


# ------------------------------------------------------------------ detector
@pytest.mark.parametrize('reply', [
    "Thik cha, ma Nepali ma bujhaunchu. Aru sodhna cha?",
    "Pani batti ko byabastha landlord le garne huncha. Aru kehi sodhna chha?",
    "Kotha herna man cha?",
    "Timro budget kati ho?",
    "Kati baje aauna sakchau?",
    "Yo herauna man lagyo bhane bhanidinu.",
    "Parking chahincha?",
])
def test_low_register_romanized_nepali_is_flagged(reply):
    assert tone.register_problems(reply, NEPALI_ROMAN)


@pytest.mark.parametrize('reply', [
    "Herna jaana chahanuhunchha?",
    "Aru kehi jannu parne bhaye sodhnuhola. Dhanyabad!",
    "Hajur ko budget kati samma ho, bhannuhola?",
    "Parking chahinchha hola?",
    "Yo viewing confirm garidiu?",
    "Team sanga confirm garera ma bhanidinchhu, huncha?",
    "Yo herauna man lagyo bhane bhanidinuhola.",
    "Chabahil ma ek ota kotha chha: PROP803052 - Rs 8,000/month.",
])
def test_respectful_romanized_nepali_passes(reply):
    assert tone.register_problems(reply, NEPALI_ROMAN) == []


def test_devanagari_low_register_flagged_and_polite_passes():
    assert tone.register_problems("तिमीलाई कस्तो कोठा चाहिन्छ? अरू सोध्न छ?", NEPALI_DEVANAGARI)
    assert tone.register_problems("हजुर, हेर्न जान चाहनुहुन्छ? अरू केही जान्नुपर्ने भए सोध्नुहोला।", NEPALI_DEVANAGARI) == []


def test_english_and_chinese_register():
    assert tone.register_problems("Budget?", 'en')
    assert tone.register_problems("Tell me the date.", 'en')
    assert tone.register_problems("Could you please tell me your budget?", 'en') == []
    assert tone.register_problems("你想看哪一個？", 'zh-TW')
    assert tone.register_problems("請問您想看哪一個？你們全家都可以來。", 'zh-TW') == []


# -------------------------------------------------------------------- polish
def test_polish_upgrades_the_screenshot_phrases_without_touching_facts():
    out = tone.polish("PROP803052 - Rs 8,000/month. Aru sodhna cha?", NEPALI_ROMAN)
    assert out == "PROP803052 - Rs 8,000/month. Aru kehi jannu parne bhaye sodhnuhola."
    assert tone.polish("Timro budget kati ho?", NEPALI_ROMAN) == "Tapai ko budget kati ho?"
    assert tone.polish("अरू सोध्न छ?", NEPALI_DEVANAGARI) == "अरू केही जान्नुपर्ने भए सोध्नुहोला।"
    assert tone.polish("Anything else?", 'en') == "Is there anything else I can help you with?"
    assert tone.polish("你好，你想看嗎？", 'zh-CN') == "您好，您想看嗎？"
    assert tone.register_problems(tone.polish("Aru sodhna cha?", NEPALI_ROMAN), NEPALI_ROMAN) == []


def test_mixed_nepali_correction_is_nepali_not_english():
    """'Actually 50 hoina, maximum 42 lakh' flipped the reply to English in the DeepSeek eval."""
    assert detect_reply_style("Actually 50 hoina, maximum 42 lakh.") == NEPALI_ROMAN


# ------------------------------------------------------------------ in the loop
def _msg(content):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=None))],
                           usage=SimpleNamespace(total_tokens=10))


@pytest.fixture
def nepal_conv(db):
    o = Organization.objects.create(name='Ghar Jagga', business_type='real_estate')
    Location.objects.create(organization=o, name='KTM', is_primary=True, is_active=True, country='Nepal')
    PropertyListing.objects.create(organization=o, title='Room with Balcony near Chabahil Chowk', description='x',
                                   listing_type='rent', property_type='room', price=Decimal('8000'),
                                   address_line1='a', city='Kathmandu', neighborhood='Chabahil')
    return Conversation.objects.create(organization=o, channel=Channel.WHATSAPP, customer_phone='9779812345678')


def _svc(conv, replies):
    svc = AIService(conv)
    svc.client = MagicMock()
    svc.client.chat.completions.create.side_effect = [_msg(r) for r in replies]
    return svc


@pytest.mark.django_db
def test_curt_draft_is_rewritten_respectfully(nepal_conv):
    text = 'chabahil ma kotha ko advance kati ho?'
    Message.objects.create(conversation=nepal_conv, sender=MessageSender.CUSTOMER, content=text)
    svc = _svc(nepal_conv, ["Advance ko kura record ma chhaina. Aru sodhna cha?",
                            "Hajur, advance ko kura record ma chhaina. Team sanga sodhera ma bhanidinchhu, huncha?"])
    out = svc.process_message(text)
    assert out['content'] == "Hajur, advance ko kura record ma chhaina. Team sanga sodhera ma bhanidinchhu, huncha?"
    # The rewrite pass is a plain completion: no tools offered, so it cannot repeat side effects.
    rewrite_call = svc.client.chat.completions.create.call_args_list[1]
    assert 'tools' not in rewrite_call.kwargs
    assert 'TONE CHECK FAILED' in rewrite_call.kwargs['messages'][-1]['content']


@pytest.mark.django_db
def test_failed_rewrite_still_sends_polished_verified_draft(nepal_conv):
    text = 'chabahil ma kotha ko advance kati ho?'
    Message.objects.create(conversation=nepal_conv, sender=MessageSender.CUSTOMER, content=text)
    # The rewrite invents a price → fails the verification gate → keep the original, polished.
    svc = _svc(nepal_conv, ["Advance ko kura record ma chhaina. Aru sodhna cha?",
                            "Hajur, advance Rs 99,999 ho."])
    out = svc.process_message(text)
    assert out['content'] == "Advance ko kura record ma chhaina. Aru kehi jannu parne bhaye sodhnuhola."
    assert '99,999' not in out['content']


@pytest.mark.django_db
def test_tone_section_is_in_every_system_prompt(nepal_conv):
    text = 'namaste'
    Message.objects.create(conversation=nepal_conv, sender=MessageSender.CUSTOMER, content=text)
    svc = _svc(nepal_conv, ["Namaste! Hajur lai kasto kotha chahiyeko ho?"])
    svc.process_message(text)
    system = svc.client.chat.completions.create.call_args.kwargs['messages'][0]['content']
    assert '# TONE' in system and 'aadarbhav' in system
