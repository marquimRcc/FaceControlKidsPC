"""PIN básico do painel. Não substitui proteção por conta/serviço do Windows."""
import secrets
import hashlib
import hmac
AUTH_SETTING="parent_pin_v1"

def hash_pin(pin: str) -> str:
    if not(pin.isdigit() and 4<=len(pin)<=12):
        raise ValueError("O PIN precisa ter de 4 a 12 dígitos.")
    salt=secrets.token_bytes(16)
    digest=hashlib.pbkdf2_hmac("sha256",pin.encode(),salt,210000)
    return f"pbkdf2_sha256:210000:{salt.hex()}:{digest.hex()}"

def verify_pin(pin: str, stored: str | None) -> bool:
    try:
        algo,iterations,salt,digest=stored.split(":")
        count=int(iterations)
        if algo!="pbkdf2_sha256" or not 100000<=count<=1000000: return False
        actual=hashlib.pbkdf2_hmac("sha256",pin.encode(),bytes.fromhex(salt),count)
        return hmac.compare_digest(actual,bytes.fromhex(digest))
    except (AttributeError, TypeError, ValueError):
        return False
