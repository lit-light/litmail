from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import imaplib
import smtplib
import email as email_lib
import json
import secrets
from datetime import datetime
from email.mime.text import MIMEText
import os

# Configuration for Migadu
IMAP_SERVER = 'imap.migadu.com'
IMAP_PORT = 993
SMTP_SERVER = 'smtp.migadu.com'
SMTP_PORT = 587

app = FastAPI()

# Enable CORS for localhost + litmail.art
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8000", "https://litmail.art", "http://localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session store (swap to Redis for production)
sessions = {}

class LoginRequest(BaseModel):
    email: str
    password: str

class SendEmailRequest(BaseModel):
    to: str
    subject: str
    body: str

class DraftRequest(BaseModel):
    to: str
    subject: str
    body: str

def create_session(email: str, password: str) -> str:
    """Create authenticated session"""
    token = secrets.token_urlsafe(32)
    sessions[token] = {'email': email, 'password': password, 'created': datetime.now()}
    return token

def get_session(token: str):
    """Get session or raise error"""
    if token not in sessions:
        raise HTTPException(status_code=401, detail='Invalid or expired session')
    return sessions[token]

@app.post('/api/login')
async def login(req: LoginRequest):
    """Authenticate with Migadu IMAP, create session"""
    email = req.email
    password = req.password
    
    try:
        # Test authentication against Migadu IMAP
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT, timeout=10)
        mail.login(email, password)
        mail.logout()
        
        # Auth successful, create session
        token = create_session(email, password)
        return {'access_token': token, 'token_type': 'bearer', 'email': email}
    except imaplib.IMAP4.error as e:
        raise HTTPException(status_code=401, detail=f'Auth failed: {str(e)}')
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Error: {str(e)}')

@app.get('/api/folder/{folder}')
async def get_folder(folder: str, token: str):
    """Fetch recent emails from specified folder (INBOX, Drafts, Sent, etc.)"""
    session = get_session(token)
    email_addr = session['email']
    password = session['password']
    
    # Validate folder names
    valid_folders = ['INBOX', 'Drafts', '[Gmail]/Sent Mail', 'Sent', 'Trash']
    if folder not in valid_folders:
        raise HTTPException(status_code=400, detail=f'Invalid folder: {folder}')
    
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT, timeout=10)
        mail.login(email_addr, password)
        
        # Try to select folder, fallback for different IMAP servers
        try:
            mail.select(folder)
        except:
            # For Migadu/Fastmail, try alternative folder names
            if folder == 'Sent':
                mail.select('[Gmail]/Sent Mail')
            elif folder == '[Gmail]/Sent Mail':
                mail.select('Sent')
            else:
                raise
        
        # Get last 10 emails
        status, messages = mail.search(None, 'ALL')
        email_ids = messages[0].split()[-10:]  # Last 10
        
        emails = []
        for email_id in reversed(email_ids):
            status, msg_data = mail.fetch(email_id, '(RFC822)')
            msg = email_lib.message_from_bytes(msg_data[0][1])
            
            # For sent/drafts, show "To" instead of "From"
            if folder in ['Sent', '[Gmail]/Sent Mail', 'Drafts']:
                from_or_to = msg.get('To', 'Unknown')
            else:
                from_or_to = msg.get('From', 'Unknown')
            
            emails.append({
                'id': email_id.decode(),
                'from': from_or_to,
                'subject': msg.get('Subject', '(no subject)'),
                'date': msg.get('Date', ''),
                'preview': msg.get_payload()[:100] if msg.get_payload() else '(empty)'
            })
        
        mail.logout()
        return {'emails': emails, 'folder': folder}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Error fetching {folder}: {str(e)}')

@app.get('/api/inbox')
async def get_inbox(token: str):
    """Fetch recent emails from inbox (legacy endpoint)"""
    session = get_session(token)
    email_addr = session['email']
    password = session['password']
    
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT, timeout=10)
        mail.login(email_addr, password)
        mail.select('INBOX')
        
        # Get last 10 emails
        status, messages = mail.search(None, 'ALL')
        email_ids = messages[0].split()[-10:]  # Last 10
        
        emails = []
        for email_id in reversed(email_ids):
            status, msg_data = mail.fetch(email_id, '(RFC822)')
            msg = email_lib.message_from_bytes(msg_data[0][1])
            
            emails.append({
                'id': email_id.decode(),
                'from': msg.get('From', 'Unknown'),
                'subject': msg.get('Subject', '(no subject)'),
                'date': msg.get('Date', ''),
                'preview': msg.get_payload()[:100] if msg.get_payload() else '(empty)'
            })
        
        mail.logout()
        return {'emails': emails}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Error fetching inbox: {str(e)}')

@app.get('/api/email/{email_id}')
async def get_email(email_id: str, token: str):
    """Fetch full email body"""
    session = get_session(token)
    email_addr = session['email']
    password = session['password']
    
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT, timeout=10)
        mail.login(email_addr, password)
        mail.select('INBOX')
        
        status, msg_data = mail.fetch(email_id.encode(), '(RFC822)')
        msg = email_lib.message_from_bytes(msg_data[0][1])
        
        body = msg.get_payload()
        if isinstance(body, list):
            body = body[0].get_payload()
        
        mail.logout()
        return {
            'id': email_id,
            'from': msg.get('From'),
            'to': msg.get('To'),
            'subject': msg.get('Subject'),
            'date': msg.get('Date'),
            'body': body
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Error fetching email: {str(e)}')

@app.post('/api/draft')
async def save_draft(req: DraftRequest, token: str):
    """Save draft to Drafts folder"""
    session = get_session(token)
    email_addr = session['email']
    password = session['password']
    
    try:
        # Create message
        msg = MIMEText(req.body)
        msg['Subject'] = req.subject
        msg['From'] = email_addr
        msg['To'] = req.to
        
        # Save to IMAP Drafts folder
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT, timeout=10)
        mail.login(email_addr, password)
        
        # Append to Drafts folder (create if doesn't exist)
        try:
            mail.select('Drafts')
        except:
            mail.create('Drafts')
            mail.select('Drafts')
        
        # Mark as draft (add \Draft flag)
        mail.append('Drafts', '\\Draft', imaplib.Time2Internaldate(datetime.now()), msg.as_bytes())
        mail.logout()
        
        return {'status': 'Draft saved successfully'}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Error saving draft: {str(e)}')

@app.post('/api/send')
async def send_email(req: SendEmailRequest, token: str):
    """Send email via Migadu SMTP and save to Sent folder"""
    session = get_session(token)
    email_addr = session['email']
    password = session['password']
    
    try:
        # Create message
        msg = MIMEText(req.body)
        msg['Subject'] = req.subject
        msg['From'] = email_addr
        msg['To'] = req.to
        
        # Send via SMTP
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10)
        server.starttls()
        server.login(email_addr, password)
        server.sendmail(email_addr, req.to, msg.as_string())
        server.quit()
        
        # Save to IMAP Sent folder
        try:
            mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT, timeout=10)
            mail.login(email_addr, password)
            
            # Try Sent folder, fallback to [Gmail]/Sent Mail
            try:
                mail.select('Sent')
                sent_folder = 'Sent'
            except:
                try:
                    mail.select('[Gmail]/Sent Mail')
                    sent_folder = '[Gmail]/Sent Mail'
                except:
                    mail.create('Sent')
                    mail.select('Sent')
                    sent_folder = 'Sent'
            
            # Append sent email to folder
            mail.append(sent_folder, '', imaplib.Time2Internaldate(datetime.now()), msg.as_bytes())
            mail.logout()
        except Exception as e:
            print(f'Warning: Could not save to Sent folder: {str(e)}')
        
        return {'status': 'Email sent successfully'}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Error sending email: {str(e)}')

@app.post('/api/logout')
async def logout(token: str):
    """Invalidate session"""
    if token in sessions:
        del sessions[token]
    return {'status': 'Logged out'}

@app.get('/health')
async def health():
    """Health check"""
    return {'status': 'OK'}

# Serve static files and frontend
if os.path.exists('static'):
    app.mount('/static', StaticFiles(directory='static'), name='static')

@app.get('/')
async def root():
    """Serve frontend"""
    return FileResponse('static/index.html')

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8888)
