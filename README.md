# LitMail Backend - FastAPI Email Client

IMAP/SMTP backend for litmail.art. Handles authentication, inbox fetching, email viewing, and sending via Migadu.

## Setup

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run server
uvicorn app:app --reload --port 8000
```

Visit http://localhost:8000/docs for interactive API docs.

### Docker

```bash
# Build & run
docker-compose up --build

# API will be at http://localhost:8000
```

## API Endpoints

### Authentication

**POST /api/login**
- Request: `{ "email": "alex@truephonetics.com", "password": "..." }`
- Response: `{ "access_token": "...", "token_type": "bearer", "email": "..." }`
- Validates credentials against Migadu IMAP, returns session token

**POST /api/logout**
- Request: `?token=<token>`
- Response: `{ "status": "Logged out" }`
- Invalidates session

### Inbox

**GET /api/inbox?token=<token>**
- Response: `{ "emails": [{ "id": "123", "from": "...", "subject": "...", "date": "...", "preview": "..." }] }`
- Fetches last 10 emails from inbox

**GET /api/email/<email_id>?token=<token>**
- Response: `{ "id": "123", "from": "...", "to": "...", "subject": "...", "date": "...", "body": "..." }`
- Fetches full email body

### Sending

**POST /api/send?token=<token>**
- Request: `{ "to": "recipient@example.com", "subject": "Subject", "body": "Message" }`
- Response: `{ "status": "Email sent successfully" }`
- Sends email via Migadu SMTP

### Health

**GET /health**
- Response: `{ "status": "OK" }`

## Session Management

- Sessions stored in-memory (swap to Redis for production)
- Session expires if unused
- Passwords only in memory during operations, never logged/stored

## Deployment

### Vercel

```bash
# Create .vercelignore (if not building Docker)
echo "venv\n__pycache__" > .vercelignore

# Deploy
vercel deploy
```

### VPS / Self-Hosted

```bash
docker-compose up -d

# Or with PM2
npm install -g pm2
pm2 start "python -m uvicorn app:app --host 0.0.0.0 --port 8000" --name litmail
```

## Environment

- IMAP: imap.migadu.com:993 (SSL)
- SMTP: smtp.migadu.com:587 (STARTTLS)
- Uses Migadu's email service

## Testing

```bash
# Login
curl -X POST http://localhost:8000/api/login \
  -H "Content-Type: application/json" \
  -d '{"email":"alex@truephonetics.com","password":"AlexPass123!@#"}'

# Get token from response, then:

# Fetch inbox
curl "http://localhost:8000/api/inbox?token=<TOKEN>"

# Send email
curl -X POST http://localhost:8000/api/send \
  -H "Content-Type: application/json" \
  -d '{"to":"recipient@example.com","subject":"Test","body":"Hello"}' \
  --get --data-urlencode "token=<TOKEN>"
```

## Frontend Integration

Frontend should:
1. POST to /api/login with credentials
2. Store access_token in session (not localStorage)
3. Include `?token=<token>` in all API requests
4. Call /api/logout on exit

## Security Notes

- Credentials only exist in memory during operations
- Session tokens should be short-lived (implement expiry)
- Use HTTPS in production
- Rate limiting recommended (add via middleware)
