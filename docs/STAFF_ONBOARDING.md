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
