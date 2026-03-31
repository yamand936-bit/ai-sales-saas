from functools import wraps
from flask import session, redirect

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect("/admin/login")
        return f(*args, **kwargs)
    return wrapper

def merchant_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("role") != "merchant":
            return redirect("/login")
        return f(*args, **kwargs)
    return wrapper
