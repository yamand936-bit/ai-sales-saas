from werkzeug.security import generate_password_hash, check_password_hash

def test_hash_password_generation():
    """Unit test for password generation in auth layer"""
    pwd = "my_secure_password"
    hashed = generate_password_hash(pwd)
    
    assert pwd != hashed
    assert check_password_hash(hashed, pwd) is True
    assert check_password_hash(hashed, "wrong_password") is False

def test_admin_auth_validation():
    """Verify admin login validation mapping mock"""
    def mock_admin_login(provided_pwd, env_pwd):
        return provided_pwd == env_pwd
        
    assert mock_admin_login("admin", "admin") is True
    assert mock_admin_login("wrong", "admin") is False
