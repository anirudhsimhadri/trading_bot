from datetime import datetime
import pytz
from ..config import settings

def is_market_open():
    est = pytz.timezone('US/Eastern')
    current_time = datetime.now(est)
    
    # Check if it's a weekday
    if current_time.weekday() >= 5:  # Saturday = 5, Sunday = 6
        return False
        
    # Check if it's during market hours
    if (current_time.hour < settings.MARKET_OPEN_HOUR or 
        current_time.hour > settings.MARKET_CLOSE_HOUR):
        return False
        
    if (current_time.hour == settings.MARKET_OPEN_HOUR and 
        current_time.minute < settings.MARKET_OPEN_MINUTE):
        return False
        
    return True
