from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
from kiteconnect import KiteConnect
from app.core.config import settings

router = APIRouter()

@router.get("/login")
def login_to_kite():
    """
    Step 1: Redirects the user to the Zerodha Kite login page.
    """
    if not settings.KITE_API_KEY:
        raise HTTPException(status_code=500, detail="KITE_API_KEY is not set in .env")
        
    kite = KiteConnect(api_key=settings.KITE_API_KEY)
    login_url = kite.login_url()
    return RedirectResponse(url=login_url)

@router.get("/callback")
def kite_callback(request_token: str):
    """
    Step 2: Zerodha redirects back here with a request_token.
    We use this to generate the final access_token for the day.
    """
    try:
        kite = KiteConnect(api_key=settings.KITE_API_KEY)
        data = kite.generate_session(request_token, api_secret=settings.KITE_API_SECRET)
        
        # The access token is valid for one entire day.
        access_token = data["access_token"]
        
        # In a production app, we would save this to the Database or Redis.
        # For now, we will just print it so you can put it in your .env file
        print("====== YOUR DAILY ACCESS TOKEN ======")
        print(access_token)
        print("=====================================")
        
        return {
            "status": "success", 
            "message": "Login successful! Check your terminal for the access token to paste into your .env file.",
            "access_token": access_token
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Login failed: {str(e)}")
