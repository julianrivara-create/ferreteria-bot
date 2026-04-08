# Slack Integration Setup Guide

## Overview

This guide explains how to integrate Slack Direct Messages with your Sales Bot Platform using Slack's Events API and Web API.

## Prerequisites

- **Slack Workspace** (admin access recommended)
- **Slack Account** (free or paid)

---

## Step 1: Create Slack App

1. Go to [Slack API Apps](https://api.slack.com/apps)
2. Click **"Create New App"**
3. Select **"From scratch"**
4. Fill in app details:
   - **App Name:** Your Bot Name (e.g., "Sales Bot")
   - **Workspace:** Select your workspace
5. Click **"Create App"**

---

## Step 2: Configure Bot Token Scopes

1. In your app dashboard, go to **"OAuth & Permissions"**
2. Scroll to **"Scopes"** → **"Bot Token Scopes"**
3. Add the following scopes:
   - ✅ `chat:write` - Send messages
   - ✅ `im:history` - Read DM history
   - ✅ `im:read` - View DM info
   - ✅ `im:write` - Send DMs
   - ✅ `users:read` - Get user info
   - ✅ `app_mentions:read` - Read @mentions (optional)

---

## Step 3: Install App to Workspace

1. Still in **"OAuth & Permissions"**, scroll to top
2. Click **"Install to Workspace"**
3. Review permissions and click **"Allow"**
4. **Copy the "Bot User OAuth Token"** (starts with `xoxb-`)
   - This is your `SLACK_BOT_TOKEN`

---

## Step 4: Get Signing Secret

1. Go to **"Basic Information"** in sidebar
2. Scroll to **"App Credentials"**
3. **Copy the "Signing Secret"**
   - This is your `SLACK_SIGNING_SECRET`

---

## Step 5: Configure Environment Variables

Add these to your `.env` file:

```bash
# Slack Integration
SLACK_BOT_TOKEN=xoxb-1234567890-1234567890-abcdefghijklmnopqrstuvwx
SLACK_SIGNING_SECRET=abcdef1234567890abcdef1234567890
SLACK_APP_TOKEN=xapp-1-XXXXX-XXXXX-XXXXX  # Optional (for Socket Mode)
```

---

## Step 6: Setup Event Subscriptions

### 6.1 Expose Your Server

If running locally, use **ngrok** to expose your server:

```bash
# Start your bot server
python3 wsgi.py

# In another terminal, start ngrok
ngrok http 8080
```

Copy the `https://` URL from ngrok (e.g., `https://abc123.ngrok-free.app`)

### 6.2 Configure Event Subscriptions

1. In your Slack app dashboard, go to **"Event Subscriptions"**
2. Toggle **"Enable Events"** to ON
3. Enter **Request URL:**
   ```
   https://your-ngrok-url.ngrok-free.app/webhook/slack
   ```
4. Wait for **"Verified ✓"** checkmark (Slack sends a challenge request)

### 6.3 Subscribe to Bot Events

Scroll to **"Subscribe to bot events"** and add:
- ✅ `message.im` - Direct messages to bot
- ✅ `app_mention` - @bot mentions in channels (optional)

5. Click **"Save Changes"**

---

## Step 7: Enable Direct Messages

1. Go to **"App Home"** in sidebar
2. Under **"Show Tabs"**, enable:
   - ✅ **Messages Tab**
   - ✅ **Allow users to send Slash commands and messages from the messages tab**

---

## Step 8: Test the Integration

### Send a Test Message

1. Open Slack app/web
2. Go to **"Apps"** in sidebar
3. Find your bot (e.g., "Sales Bot")
4. Send a DM: **"Hola"**
5. The bot should respond with a greeting

### Check Logs

```bash
# Watch server logs
tail -f logs/bot.log

# You should see:
# Slack message from U12345678: Hola
# 💬 Slack message sent to D12345678
```

---

## Troubleshooting

### Webhook Verification Fails

**Error:** "Your URL didn't respond with the value of the challenge parameter"

**Solution:**
- Ensure your server is running (`python3 wsgi.py`)
- Check ngrok is forwarding to the correct port
- Verify `SLACK_BOT_TOKEN` and `SLACK_SIGNING_SECRET` are set
- Check server logs for errors

### Bot Doesn't Respond

**Error:** Messages sent but no response

**Checklist:**
1. Check `SLACK_BOT_TOKEN` is set correctly
2. Verify bot has `chat:write` and `im:write` scopes
3. Check event subscriptions include `message.im`
4. Review server logs for errors
5. Verify signature verification is passing

### "Invalid Signature"

**Error:** Slack signature verification failed

**Solution:**
- Ensure `SLACK_SIGNING_SECRET` matches the one in Slack dashboard
- Check system time is synchronized (signature uses timestamp)
- Verify request is not older than 5 minutes

### "Missing Scope"

**Error:** `missing_scope` in API response

**Solution:**
- Go to **"OAuth & Permissions"** → **"Scopes"**
- Add the missing scope (e.g., `chat:write`)
- **Reinstall the app** to workspace (required after scope changes)

---

## Production Deployment

### Use Environment Variables

On Railway/Heroku/VPS, set environment variables:

```bash
# Railway
railway variables set SLACK_BOT_TOKEN=xoxb-...
railway variables set SLACK_SIGNING_SECRET=...

# Heroku
heroku config:set SLACK_BOT_TOKEN=xoxb-...
heroku config:set SLACK_SIGNING_SECRET=...
```

### Update Event Subscription URL

When deploying to production, update the Request URL in Slack:
- **Development:** `https://abc123.ngrok-free.app/webhook/slack`
- **Production:** `https://your-domain.com/webhook/slack`

---

## Advanced Features

### Interactive Components (Buttons)

Enable interactive messages:

1. Go to **"Interactivity & Shortcuts"**
2. Toggle **"Interactivity"** to ON
3. Enter **Request URL:** `https://your-url/webhook/slack/interactive`
4. Click **"Save Changes"**

**Example: Send buttons**
```python
from bot_sales.connectors.slack import get_slack_connector

connector = get_slack_connector()
connector.send_quick_replies(
    channel="D12345678",
    text="¿Qué producto te interesa?",
    options=["Herramienta", "Sierra Circular", "Lijadora Orbital"]
)
```

### Socket Mode (Alternative to Webhooks)

For local development without ngrok:

1. Go to **"Socket Mode"** in sidebar
2. Toggle **"Enable Socket Mode"** to ON
3. Generate **App-Level Token** with `connections:write` scope
4. Copy token (starts with `xapp-`) to `SLACK_APP_TOKEN`

**Note:** Socket Mode requires `slack-bolt` SDK (not implemented in basic connector)

---

## Security Best Practices

1. **Always verify signatures** (already implemented in connector)
2. **Never commit tokens** to Git
3. **Use environment variables** for all secrets
4. **Rotate tokens** if compromised
5. **Use HTTPS** in production (required by Slack)

---

## Rate Limits

Slack has tiered rate limits:

| Tier | Limit | Notes |
|------|-------|-------|
| Tier 1 | 1/min | New apps |
| Tier 2 | 20/min | After initial usage |
| Tier 3 | 50/min | Established apps |
| Tier 4 | 100+/min | High-volume apps |

**Mitigation:** Implement request queuing for high-volume scenarios

---

## API Reference

- [Slack Events API](https://api.slack.com/apis/connections/events-api)
- [Slack Web API](https://api.slack.com/web)
- [Block Kit Builder](https://app.slack.com/block-kit-builder) - Design rich messages
- [Slack API Methods](https://api.slack.com/methods)

---

## Support

If you encounter issues:
1. Check [Slack API Community](https://api.slack.com/community)
2. Review server logs: `tail -f logs/bot.log`
3. Test webhook manually:
   ```bash
   curl -X POST https://your-url/webhook/slack \
     -H "Content-Type: application/json" \
     -d '{"type": "url_verification", "challenge": "test123"}'
   ```
4. Use [Slack API Tester](https://api.slack.com/methods/api.test/test)
