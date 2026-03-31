import os
os.environ["SUPERADMIN_PASSWORD"] = "test"
os.environ["FLASK_SECRET_KEY"] = "test"
os.environ["ENCRYPTION_KEY"] = "IWfZ56p9EFT0xU09HHDPZdzlPC5sPezp1PrWoD9UjAE="

try:
    from src.main import app
    print("Application successfully parsed and loaded all blueprints!")
except Exception as e:
    import traceback
    traceback.print_exc()
