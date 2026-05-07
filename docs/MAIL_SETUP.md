# Mail Channel — Setup Guide (Gmail OAuth)

This guide assumes **zero prior knowledge** of Google Cloud Console.
Follow every step in order; skipping one will cause cryptic errors later.

---

## 1. Create a Google Cloud Project

1. Go to [https://console.cloud.google.com/](https://console.cloud.google.com/).
2. Sign in with the Google account that owns the Gmail inbox the bot will read
   (e.g. the ferreteria business account).
3. Click the project selector at the top of the page → **New Project**.
4. Name it something memorable, e.g. `ferreteria-bot`.
5. Click **Create** and wait ~10 seconds for it to be provisioned.
6. Make sure the new project is selected in the top bar before continuing.

---

## 2. Enable the Gmail API

1. In the left menu go to **APIs & Services → Library**.
2. Search for `Gmail API`.
3. Click the result → **Enable**.

You will land on the Gmail API overview page. The API is now active.

---

## 3. Configure the OAuth Consent Screen

This step defines what Google shows users when they authorise the bot.

1. Go to **APIs & Services → OAuth consent screen**.
2. **User Type** — choose one:
   - **Internal** — if your Google account is a Google Workspace account
     (paid G Suite / Workspace org). Only people in your org can authorise.
     Recommended if available.
   - **External** — if it is a personal Gmail account. The app will start
     in "Testing" mode, which is fine — you don't need to publish it.
3. Click **Create**.
4. Fill in the required fields:
   - **App name**: `Ferreteria Bot Mail`
   - **User support email**: your email
   - **Developer contact information**: your email
5. Click **Save and Continue**.
6. **Scopes** page → click **Add or Remove Scopes**.
   Search for and add both:
   - `https://www.googleapis.com/auth/gmail.readonly`
   - `https://www.googleapis.com/auth/gmail.modify`
   Click **Update** → **Save and Continue**.
7. **Test Users** (only appears for External type):
   Click **Add Users** → add `julianrivara@gmail.com` (and any other accounts
   that will run the bot). Click **Save and Continue**.
8. Review the summary → **Back to Dashboard**.

---

## 4. Create OAuth Credentials

1. Go to **APIs & Services → Credentials**.
2. Click **+ Create Credentials → OAuth client ID**.
3. **Application type**: select **Desktop app**.
4. **Name**: `ferreteria-bot-desktop` (anything is fine).
5. Click **Create**.
6. A dialog appears with your Client ID and Client Secret. Click
   **Download JSON** (or the download icon in the credentials list).
7. Rename the downloaded file to `credentials.json`.

---

## 5. Place credentials.json in the Repo

Copy `credentials.json` to the **root of the ferreteria repo**:

```
ferreteria/
├── credentials.json   ← here
├── app/
├── bot_sales/
...
```

> **Security**: `credentials.json` is listed in `.gitignore`.
> Never commit it. It contains your OAuth client secret.

If you want to use a custom path, set the env var:
```bash
export GMAIL_CREDENTIALS_PATH=/path/to/your/credentials.json
export GMAIL_TOKEN_PATH=/path/to/your/token.json
```

---

## 6. First Login

From the repo root, run:

```bash
python -m app.mail login
```

This will:
1. Open a browser window showing Google's OAuth consent screen.
2. Ask you to select the Google account associated with the Gmail inbox.
3. Show a warning "Google hasn't verified this app" — click **Continue**.
4. Ask you to grant the two scopes (readonly + modify) — click **Allow**.
5. Close the browser tab (or it closes automatically).
6. Print `Authentication successful. Token saved to: token.json`.

`token.json` is now in the repo root. It is also in `.gitignore`.

---

## 7. Verify It Works

List the last 10 unread messages:

```bash
python -m app.mail list-unread
```

You should see a table like:

```
ID                   FROM                                SUBJECT
------------------------------------------------------------------------------------------
18f3a1b2c3d4e5f6     Juan Perez <juan@example.com>      Pedido de materiales
    Hola, quiero cotizar 3 mechas 8mm...
```

Show a full message (copy an ID from the list):

```bash
python -m app.mail show 18f3a1b2c3d4e5f6
```

---

## 8. Troubleshooting

### "credentials.json not found"
The file is missing or in the wrong place. It must be at the repo root
(or at the path set by `GMAIL_CREDENTIALS_PATH`).

### "Token expired and refresh failed"
The refresh token was revoked (e.g. you changed the scopes or revoked
access from Google Account settings). Delete `token.json` and re-run login:

```bash
python -m app.mail logout
python -m app.mail login
```

### "Access blocked: This app's request is invalid" or scope errors
The scopes in the credentials don't match what the code requests. Go back
to step 3, verify both `gmail.readonly` and `gmail.modify` are listed under
**Scopes**, save, and repeat the login.

### "This app isn't verified" warning (External user type)
This is expected for a personal project. Click **Advanced → Go to
Ferreteria Bot Mail (unsafe)**. You only need to do this once.

### "Error 403: access_denied"
Your Google account is not in the **Test Users** list (External apps only).
Go to **OAuth consent screen → Test Users → Add Users**, add your Gmail
address, and re-run login.

### Token refresh stops working after 7 days (External apps in Testing mode)
Google revokes refresh tokens for unverified External apps after 7 days.
This is a Google policy limitation. Options:
- Switch to **Internal** if you have Google Workspace.
- Re-run `python -m app.mail login` every 7 days.
- Publish the app (requires Google verification — overkill for internal use).

---

## 9. Removing Access

To revoke the bot's access to the Gmail account at the Google level:

1. Go to [https://myaccount.google.com/permissions](https://myaccount.google.com/permissions).
2. Find `Ferreteria Bot Mail` → **Remove Access**.

To clear the local token:

```bash
python -m app.mail logout
```
