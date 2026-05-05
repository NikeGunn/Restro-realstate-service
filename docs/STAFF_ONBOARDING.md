# Kribaat Staff Onboarding Guide

A field manual for Kribaat staff who set up new customer accounts on-site.

> **Audience:** Kribaat field staff onboarding restaurants and real-estate
> agencies onto kribaat.com.
> **Time per customer:** ~10–15 minutes if Twilio is used.
> **What to bring:** A laptop, a phone with WhatsApp, and the customer's
> business email.

---

## Onboarding flow at a glance

```
1. Create the customer's Kribaat account     (2 min)
2. Set up their organization profile         (3 min)
3. Add knowledge base content                (3 min)
4. Connect WhatsApp via Twilio Sandbox       (5 min)
5. Test end-to-end                           (2 min)
```

---

## Step 1 — Create the customer's Kribaat account

1. Open **https://kribaat.com/register**
2. Fill in:
   - Full name (the customer's name)
   - Email (the customer's business email — they will receive everything here)
   - A temporary password (give them this; they'll change it later)
3. Have the customer verify their email if a verification link is sent.
4. Log in at **https://kribaat.com/login** with their new credentials.

> **Tip:** Always create the account on the customer's actual email, not your
> own. They need to be able to log in after you leave.

---

## Step 2 — Set up the organization profile

After first login, the dashboard prompts for organization setup.

1. **Organization name** — the customer's brand name (e.g. *"Bagaicha
   Restaurant"*).
2. **Business type** — pick *Restaurant* or *Real Estate*. This decides
   which features appear in the dashboard. **You cannot change this later
   without Kribaat support**, so confirm with the customer.
3. **Plan** — start on *Basic*. Upgrade to *Power* later if they want
   Instagram support.
4. Click **Create Organization**.

After this, in the **Settings → Profile** page, fill in:

- Business address
- Business phone (their public number)
- Default greeting message (what the bot says first; e.g.
  *"Hi! Welcome to Bagaicha. How can I help?"*)
- Business hours (used by the bot to answer "are you open?")

---

## Step 3 — Add knowledge base content

Go to **Knowledge** in the sidebar.

The AI **only answers from this content**. If it's empty, the bot will
escalate every question to a human. Bare minimum to add:

**Restaurant**
- Menu (item name, price, description)
- Hours and any closed days
- Address + parking info
- Booking policy (deposit? cancellation window?)
- Top FAQs ("Do you serve halal?", "Is there outdoor seating?")

**Real estate**
- Active listings (with price, beds/baths, area, neighborhood)
- Service areas
- Agent contact info
- FAQs ("Do you handle commercial?", "What documents do I need?")

> **Tip:** Aim for at least 10 FAQ entries on day one. The bot's answer
> quality is directly proportional to KB depth.

---

## Step 4 — Connect WhatsApp via Twilio (Sandbox)

This is the most error-prone step. Follow it exactly.

### 4a. Create the customer's Twilio account

1. Open a new browser tab → **https://www.twilio.com/try-twilio**
2. Sign up with the customer's business email (same one used for Kribaat).
3. Verify the email link Twilio sends.
4. Verify a phone number — **use the customer's phone**, not yours.
5. When Twilio asks "What do you want to build?" answer:
   - *Which Twilio product are you here to use?* → **Messaging**
   - *What do you want to build?* → **Chatbot / Assistant**
   - *How do you want to build it?* → **With code**
   - *Preferred language* → **Python**
6. Skip any other onboarding questions ("Get started in console").

### 4b. Get the Account SID + Auth Token

This is where most people get lost. **Do NOT use the User Settings page**
(`/user/user-settings/overview`) — the `US...` "User SID" there is not
what we need.

1. After Twilio signup, you land on the **Twilio Console homepage**:
   **https://console.twilio.com**
2. Scroll down on that homepage to the **"Account Info"** card.
3. Two values are shown:
   - **Account SID** — starts with **`AC`** followed by 32 hex characters.
     Click the **copy icon** next to it.
   - **Auth Token** — hidden by default. Click **"Show"** or the eye icon,
     then copy.

Direct link if the homepage card is not visible:
**https://console.twilio.com/us1/account/keys-credentials/api-keys**
(switch from "API Keys" tab to "Live Credentials" tab; Account SID +
Auth Token are at the top.)

OR

Goto: https://console.twilio.com/?frameUrl=%2Fconsole%3Fx-target-region%3Dus1

> **Auth Token = production secret.** Never paste it into Slack, email, a
> screenshot, or chat. Paste it directly into Kribaat and close the tab.

### 4c. Open Twilio's WhatsApp Sandbox

1. In Twilio Console, left sidebar → **Messaging → Try it out → Send a
   WhatsApp message**.
   Direct link: **https://console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn**
2. You'll see a page titled **"Try WhatsApp"** with two values:
   - **Sandbox number** — almost always `+1 415 523 8886`. Write it down.
   - **Join code** — a two-word phrase, e.g. `join using-pink`. Write down
     just the second word (here: `using-pink`).
3. On the same page, switch to the **"Sandbox settings"** tab.
4. In **"When a message comes in"**:
   - Method: **POST**
   - URL: paste **`https://kribaat.com/api/webhooks/twilio/`**
   - (You'll copy this exact URL from the Kribaat dashboard in step 4d —
     use the copy button there to be safe.)
5. Click **Save** at the bottom of the Sandbox settings page.

### 4d. Connect inside Kribaat

1. In Kribaat dashboard → **Settings → Channels → "Twilio (Easy Setup)"
   tab**.
2. Confirm the **Webhook URL** at the top matches what you pasted into
   Twilio. Use the copy button to grab it.
3. Click **"Connect Twilio WhatsApp (recommended)"**.
4. Fill the form:
   - **Account SID** → paste the `AC...` value (step 4b).
   - **Auth Token** → paste the hidden value (step 4b).
   - **From Number** → leave as `+14155238886` unless Twilio gave you a
     different sandbox number.
   - **Sandbox Join Code** → just the word/phrase (e.g. `using-pink`).
     Do NOT include the word "join".
   - **"This is a Twilio Sandbox sender"** → keep checked.
5. Click **Save & Activate**.

If credentials are valid, the badge flips to **"Verified"** within seconds.

> **If "Verified" doesn't appear:**
> - Re-check the Account SID starts with `AC` (not `US`, not `SK`).
> - Auth Token has no leading/trailing spaces (paste, then re-paste).
> - In Twilio Console, confirm the account is not suspended (free trials
>   sometimes pause until phone-verified).

---

## Step 5 — End-to-end test

1. **On the customer's phone** (the one verified with Twilio):
   - Open WhatsApp, start a new chat with **+1 415 523 8886**.
   - Send: **`join using-pink`** (replace with their actual code).
   - Twilio replies confirming sandbox membership.
2. **Send a real question** to the same number, e.g.
   *"What time do you open?"* or *"Do you have any 2-bedroom listings?"*.
3. Within 5 seconds, the AI should reply.
4. Open Kribaat dashboard → **Inbox** → you should see the conversation
   live.
5. From the dashboard, send a manual reply — it should arrive on WhatsApp
   instantly.

If all four work, you're done.

---

## ⚠️ Twilio Sandbox limits — what staff and customers must know

The Sandbox is for **testing only**. It has hard limits that cannot be removed
without migrating to a production WhatsApp Sender. Make sure the customer
understands these before you walk away.

### What expires (and what doesn't)

| Item | Expires? | Notes |
|---|---|---|
| Account SID | Never | Permanent identifier |
| Auth Token | Never (unless rotated manually) | Treat as a password — store securely |
| Sandbox number `+14155238886` | Never | Shared by all Twilio Sandbox users globally |
| **A customer's right to message your bot** | **After 72 hours of inactivity** | They must send `join <code>` again to resume |
| Twilio trial credit | When spent | Trial accounts get ~$15 USD; messages cost ~$0.005 each |

### The 72-hour rule (most important to understand)

After a customer sends `join <code>` to opt in, they have a 72-hour rolling
window to message the bot. **Each new message resets the clock by another
72 hours.** If they go quiet for 3 full days, Twilio drops them and they
must re-join with `join <code>`.

This is enforced by Meta (WhatsApp's owner) on all sandbox usage globally —
Twilio cannot waive it.

**For active daily users this is invisible** — they message every day, the
window keeps rolling, they never notice. **For occasional users** (someone
who messages once a week) this is painful — they have to remember the join
code every time.

### When the customer should upgrade to production

Recommend production migration when ANY of these is true:

- Customer plans to advertise the WhatsApp number publicly (e.g. on a website,
  flyer, or Google listing)
- Customer expects walk-up customers (people who haven't pre-joined) to chat
- Customer wants to use their own branded business phone number, not
  `+1 415 523 8886`
- Customer has more than ~50 daily WhatsApp conversations
- Customer wants to send templated messages, marketing notifications, or
  proactive messages outside the 24-hour reply window

### How to migrate from Sandbox to production WhatsApp Sender

> Estimated time: **1–2 weeks** (Meta does the slow part — WhatsApp Business
> verification). Cost: a Twilio phone number (~$1/mo) plus per-message fees.

**Step 1 — Verify the customer's Facebook Business**
1. Go to https://business.facebook.com → Business Settings
2. Customer's business must be a real registered entity with a website,
   email, and a public phone number that matches business records.
3. Submit "Business Verification" (upload registration certificate, utility
   bill, etc.). Approval takes 1–7 days typically.

**Step 2 — In Twilio Console, request a WhatsApp Sender**
1. Twilio Console → **Messaging → Senders → WhatsApp Senders → New WhatsApp
   Sender**.
2. Pick the Twilio phone number you want to use for WhatsApp (or buy a new
   one from Twilio).
3. Twilio walks you through linking it to the customer's verified Facebook
   Business Manager.
4. Choose a display name (the name customers see — must be related to the
   actual business name; Meta reviews it).
5. Submit. Meta approves the sender within 1–3 days after Business
   Verification is done.

**Step 3 — Update the Kribaat config**
1. Once Meta approves the sender, the new WhatsApp number is live.
2. In Kribaat → Settings → Channels → Twilio tab → edit the existing config:
   - Change **From Number** to the new approved number
   - **Uncheck** "This is a Twilio Sandbox sender"
   - Clear the **Sandbox Join Code** field (no longer needed)
   - Save
3. In Twilio Console, configure the inbound webhook on the new sender:
   **Messaging → Senders → [your-sender] → Configure → Inbound URL**:
   `https://kribaat.com/api/webhooks/twilio/` (POST). Save.
4. Test by messaging the new number from any phone — no `join` code needed.

**Step 4 — Decommission Sandbox (optional)**
Once production works, the customer can ignore the Sandbox. They don't need
to remove the Sandbox config — it just sits unused. If you want to clean
up, delete the Sandbox config row from Kribaat and tell existing testers
to stop messaging `+1 415 523 8886`.

### Meanwhile — keeping the Sandbox alive for staff testing

If you're using the Sandbox just for internal testing while Meta verification
is pending, here's how to keep your test number from getting kicked out:

- Send any message to the bot at least once every 72 hours
- Or add a calendar reminder for the staff phone every 2 days
- Or have any team member text the bot — same join code, multiple devices

There is **no way to extend the 72-hour window from our side** — it's
enforced by Meta.

---

## Setting up Instagram (Power plan only)

Unlike WhatsApp, **Instagram has no sandbox shortcut**. Every customer must
have a real Facebook Business + Instagram Business setup. Plan for ~30
minutes per customer for this step. Twilio cannot help here — Instagram
requires direct Meta integration.

### Prerequisites

- Customer is on **Power plan** (Basic plan blocks Instagram setup)
- Customer has a **Facebook Business Manager** account
- Customer's **Instagram is converted to a Business or Creator account**
  (not a personal account)
- Instagram is **linked to a Facebook Page** the customer owns
- Customer is admin of both the Page and the Instagram account

If any of these is false, walk through the Facebook Business setup first
(or hand off to the customer's social-media person — it's not really our
domain to set up their Facebook Business).

### Step-by-step

1. **Create a Meta Developer App**
   - Go to https://developers.facebook.com/apps → **Create App** → "Business"
   - App name: `<Customer Name> - Kribaat Bot`
   - Add the **Instagram** product to the app
   - Add the **Webhooks** product to the app
   - Copy the **App Secret** from the app's settings — Kribaat needs this
     in the `META_APP_SECRET` env var (this is configured cluster-wide,
     not per-customer; ping engineering if it's not set)

2. **Get the Instagram Business Account ID**
   - Tools → Graph API Explorer
   - Use the customer's User Access Token, query: `me/accounts` → find the
     Page → use that Page Access Token to query
     `<page-id>?fields=instagram_business_account`
   - Copy the `instagram_business_account.id` → that's the
     **Instagram Business ID** for Kribaat

3. **Get a Long-Lived Page Access Token**
   - Graph API Explorer → use Page Access Token (NOT user)
   - Token → "Get Long-Lived Access Token" (extends to ~60 days)
   - Or even better: request `pages_messaging` permission and exchange for
     a never-expiring system-user token via Business Settings

4. **In Kribaat → Settings → Channels → Instagram tab:**
   - Instagram Business ID: paste from step 2
   - Page ID: the linked Facebook Page's ID
   - Access Token: paste the long-lived token from step 3
   - Verify Token: leave the default (Kribaat auto-generates one)
   - Save

5. **Configure the webhook in Meta**
   - In your Meta App → Webhooks → Instagram → Edit Subscription
   - Callback URL: `https://kribaat.com/api/webhooks/instagram/`
   - Verify Token: paste the verify token from Kribaat (visible after save)
   - Subscribe to: `messages`, `messaging_postbacks`
   - Click "Verify and Save" → if Kribaat's "is_verified" badge flips to
     green, you're done

6. **Test:** Send a DM to the customer's Instagram account from another
   account. Bot should reply within 5 seconds.

### Instagram token expiry — the big gotcha

Page access tokens commonly **expire in 60 days**. If you walk away and
forget to set up a permanent token, Instagram will silently stop replying
in two months and the customer won't know why.

To make Instagram permanent:

- Go to **Business Settings → Users → System Users** → create a system
  user for the integration
- Generate a token with `pages_messaging` and `instagram_basic` permissions
  → no expiry
- Paste this into Kribaat instead of the short-lived token

If a token does expire, the customer will see no replies on Instagram and
Kribaat → Channels → Instagram tab → Health Check will report a token
error. Just generate a fresh token in Business Settings and update the
config.

### Instagram limits (Meta's rules, not ours)

- 24-hour customer service window: bot can only reply within 24h of the
  customer's last message
- No proactive outbound messages without an approved message tag
- Cannot DM users who haven't messaged the customer first

---

## Common problems and fixes

| Symptom | Cause | Fix |
|---|---|---|
| AI doesn't reply on WhatsApp | KB is empty → AI escalates everything | Add at least 10 FAQ entries |
| "Test message" button fails with "Twilio rejected" | Auth Token wrong, or recipient hasn't joined sandbox | Re-paste token; ask recipient to send `join <code>` |
| Webhook receives nothing in Twilio's debugger | Wrong URL pasted in Sandbox Settings | Copy URL again from Kribaat → Channels tab |
| Sent fine but customer never sees the reply | Recipient never joined sandbox | They must send `join <code>` first; sandbox limitation |
| Bot replies in wrong language | Multilingual detection works only after the first 1–2 messages | Continue chatting; it learns by message 3 |
| "Verified" badge stays gray | Twilio account not phone-verified | Complete phone verification in Twilio Console |
| Customer wants to use their own number | Sandbox is for testing only | Customer must apply for a Twilio approved WhatsApp Sender (separate process; 1–2 weeks via Twilio) |

---

## What to leave with the customer

Before leaving, confirm:

- [ ] Customer can log in to kribaat.com with their own credentials
- [ ] Customer changed the temporary password
- [ ] At least 10 KB / FAQ entries are loaded
- [ ] WhatsApp test exchange round-tripped successfully
- [ ] Customer's phone has joined the Twilio sandbox
- [ ] Twilio account email + password are saved by the customer (not us)
- [ ] Customer has the support number for Kribaat

Print and hand over the **one-pager** on the next page.

---

## Customer one-pager (tear-off)

> **Welcome to Kribaat!**
>
> Your AI WhatsApp assistant is live.
>
> **To chat with your bot:**
> Send a WhatsApp message to **+1 415 523 8886**.
> First message must be: `join <your-code>`.
>
> **To manage everything:**
> Visit **https://kribaat.com/login**.
> Add menu items, listings, FAQs, and check Inbox there.
>
> **Important — Twilio Sandbox limits:**
> While in Sandbox, only people who send `join <code>` can reach your
> bot. To open it to all customers, ask Kribaat support about upgrading
> to a production WhatsApp sender (~1–2 week process via Twilio).
>
> **Need help?** Email support@kribaat.com

---

## Internal-only: Verifying an account from the back-end

If a customer reports their account is broken, you can run this from
inside the production cluster (requires kubectl access):

```bash
kubectl exec -n chatplatform deploy/backend -- \
  python manage.py verify_account --email customer@example.com
```

Output shows:
- Whether the user exists and is active
- Their organization(s), plan, and business type
- Whether default Location exists (auto-created if not)
- Status of WhatsApp(Meta), Twilio, Instagram channels
- KnowledgeBase / FAQ counts

This command is idempotent — run it as often as you need.

---

## Escalation

| What happened | Who to ping |
|---|---|
| Customer's Twilio account is suspended | Twilio support — out of our control |
| Webhook never receives anything, but Twilio says it's sending | Kribaat engineering — possible infra issue |
| Customer wants to switch from Twilio to Meta WhatsApp Business | Kribaat engineering — manual migration needed |
| Customer wants Instagram | Upgrade plan to Power, then use the Instagram tab in Channels |
| AI is replying with nonsense or hallucinations | Kribaat AI team — likely KB content issue |
