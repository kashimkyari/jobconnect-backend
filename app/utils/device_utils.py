import httpx
from fastapi import Request

def get_client_ip(request: Request) -> str:
    # Handle proxies like Nginx or generic Load Balancers
    x_forwarded_for = request.headers.get("x-forwarded-for")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    
    x_real_ip = request.headers.get("x-real-ip")
    if x_real_ip:
        return x_real_ip.strip()
        
    return request.client.host if request.client else ""

def parse_user_agent(ua_string: str, custom_name: str = "", custom_type: str = "") -> dict:
    if not ua_string:
        return {"device_name": "Unknown Device", "device_type": "unknown"}
    
    ua_lower = ua_string.lower()
    
    device_type = "desktop"
    if any(mobi in ua_lower for mobi in ["mobi", "android", "iphone"]):
        device_type = "mobile"
    if any(tab in ua_lower for tab in ["tablet", "ipad"]):
        device_type = "tablet"
        
    device_name = "Unknown Device"
    if "iphone" in ua_lower:
        device_name = "iPhone"
    elif "ipad" in ua_lower:
        device_name = "iPad"
    elif "mac os x" in ua_lower or "macintosh" in ua_lower:
        device_name = "Mac"
    elif "windows" in ua_lower:
        device_name = "Windows PC"
    elif "android" in ua_lower:
        device_name = "Android Device"
    elif "linux" in ua_lower:
        device_name = "Linux PC"
        
    if custom_name:
        device_name = custom_name
    if custom_type:
        device_type = custom_type
        
    return {
        "device_name": device_name,
        "device_type": device_type
    }

async def get_location_from_ip(ip: str) -> str:
    if not ip or ip in ["127.0.0.1", "::1", "localhost"]:
        return "Local Network"
    
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"http://ip-api.com/json/{ip}")
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    city = data.get("city", "")
                    country = data.get("country", "")
                    if city and country:
                        return f"{city}, {country}"
                    elif country:
                        return country
    except Exception:
        pass
    
    return "Unknown Location"
