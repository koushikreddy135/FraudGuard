"""
Selenium UI tests for the FraudGuard web app (login, registration, RBAC, lockout, logout, Google button).

Before running, start the app (two terminals):
    python -m uvicorn backend.test_app:build_auth_app --factory --port 8000     (project root)
    npm run dev                                                                 (frontend folder, port 5173)

Run:
    python -m pytest tests\\test_ui_selenium.py -v

Admin tests need an admin account. Create one once (any strong password), then tell the tests about it:
    python -m backend.bootstrap_admin --email admin@fraudguard.local --name "Admin" --password "Admin#2026pass"
    set ADMIN_EMAIL=admin@fraudguard.local
    set ADMIN_PASSWORD=Admin#2026pass
Without these two variables the admin tests are skipped.

Optional:  set BASE_URL=http://localhost:5173   set HEADLESS=1 (no browser window)
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait

# For recording a demo video:  set SLOW=0.7   (seconds of pause before every click / typing). Default 0 = full speed.
SLOW = float(os.environ.get("SLOW", "0"))
if SLOW:
    _orig_click, _orig_keys = WebElement.click, WebElement.send_keys

    def _slow_click(self):
        time.sleep(SLOW)
        return _orig_click(self)

    def _slow_keys(self, *value):
        time.sleep(SLOW / 2)
        return _orig_keys(self, *value)

    WebElement.click, WebElement.send_keys = _slow_click, _slow_keys

BASE =os.environ.get("BASE_URL", "http://localhost:5173").rstrip("/")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
CUSTOMER_PASSWORD = "Strong#Pass2026"


# ------------------------------------------------------------------ helpers
def api(path, body=None, method=None):
    """Call the backend through the frontend's /api proxy. Returns (status, json)."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method or ("POST" if body is not None else "GET"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def new_customer():
    email = f"ui_{uuid.uuid4().hex[:10]}@example.com"
    status, _ = api("/api/auth/register/customer", {
        "full_name": "Selenium Tester", "email": email,
        "password": CUSTOMER_PASSWORD, "confirm_password": CUSTOMER_PASSWORD})
    assert status == 201, "could not create test customer"
    return email


@pytest.fixture
def browser():
    opts = webdriver.ChromeOptions()
    if os.environ.get("HEADLESS") == "1":
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1366,900")
    d = webdriver.Chrome(options=opts)
    yield d
    if SLOW:
        time.sleep(SLOW * 3)       # let the final page stay on screen before the browser closes
    d.quit()


def wait(d, seconds=10):
    return WebDriverWait(d, seconds)


def text_visible(d, text, seconds=10):
    wait(d, seconds).until(EC.visibility_of_element_located((By.XPATH, f"//*[contains(normalize-space(.), {json.dumps(text)})]")))


def fill_login(d, email, password):
    wait(d).until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[type=email]")))
    d.find_element(By.CSS_SELECTOR, "input[type=email]").clear()
    d.find_element(By.CSS_SELECTOR, "input[type=email]").send_keys(email)
    d.find_element(By.CSS_SELECTOR, "input[type=password]").clear()
    d.find_element(By.CSS_SELECTOR, "input[type=password]").send_keys(password)
    d.find_element(By.CSS_SELECTOR, "button[type=submit]").click()


def customer_login(d, email, password=CUSTOMER_PASSWORD):
    d.get(BASE + "/login")
    fill_login(d, email, password)


def admin_login(d):
    d.get(BASE + "/admin/login")
    fill_login(d, ADMIN_EMAIL, ADMIN_PASSWORD)


needs_admin = pytest.mark.skipif(not (ADMIN_EMAIL and ADMIN_PASSWORD),
                                 reason="set ADMIN_EMAIL and ADMIN_PASSWORD to run admin tests")


# ------------------------------------------------------------------ pages load
def test_customer_login_page_loads(browser):
    browser.get(BASE + "/login")
    text_visible(browser, "Welcome back")
    assert browser.find_element(By.CSS_SELECTOR, "input[type=email]").is_displayed()
    assert browser.find_element(By.CSS_SELECTOR, "input[type=password]").is_displayed()
    text_visible(browser, "Sign in to Portal")


def test_register_page_loads(browser):
    browser.get(BASE + "/login")
    browser.find_element(By.LINK_TEXT, "Create an account").click()
    wait(browser).until(EC.url_contains("/register"))
    text_visible(browser, "Complete Registration")


def test_admin_login_page_loads(browser):
    browser.get(BASE + "/admin/login")
    text_visible(browser, "Admin Sign In")
    text_visible(browser, "Authorize Operator Session")


# ------------------------------------------------------------------ Google OAuth
def test_google_button_is_shown(browser):
    browser.get(BASE + "/login")
    text_visible(browser, "Continue with Google")


def test_google_button_starts_oauth_or_explains(browser):
    """If Google keys are in .env the button must go to Google; if not, the page must say OAuth is not configured."""
    _, info = api("/api/auth/oauth/google/url")
    browser.get(BASE + "/login")
    wait(browser).until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Continue with Google')]"))).click()
    if info["configured"]:
        wait(browser, 15).until(EC.url_contains("accounts.google.com"))
    else:
        text_visible(browser, "not configured")


def test_google_url_has_state_and_redirect_uri():
    """OAuth security: every login URL carries a fresh random state (CSRF protection) and the registered redirect URI."""
    status, first = api("/api/auth/oauth/google/url")
    assert status == 200
    if not first["configured"]:
        pytest.skip("Google OAuth keys are not in .env")
    _, second = api("/api/auth/oauth/google/url")
    q1 = urllib.parse.parse_qs(urllib.parse.urlparse(first["url"]).query)
    q2 = urllib.parse.parse_qs(urllib.parse.urlparse(second["url"]).query)
    assert q1["response_type"] == ["code"]
    assert "openid" in q1["scope"][0]
    assert q1["redirect_uri"][0].endswith("/api/auth/oauth/google/callback")
    assert len(q1["state"][0]) >= 16
    assert q1["state"] != q2["state"], "state must be different for every login"


def test_oauth_callback_rejects_wrong_state(browser):
    """A callback with a state that does not match our cookie must be refused (CSRF protection)."""
    browser.get(BASE + "/api/auth/oauth/google/callback?code=fake&state=not-the-real-state")
    wait(browser).until(EC.url_contains("/login"))
    text_visible(browser, "Invalid or expired OAuth state")


# ------------------------------------------------------------------ visitors are blocked
def test_visitor_cannot_open_customer_portal(browser):
    browser.get(BASE + "/customer")
    wait(browser).until(EC.url_contains("/login"))
    assert "/customer" not in browser.current_url


def test_visitor_cannot_open_admin_portal(browser):
    browser.get(BASE + "/admin")
    wait(browser).until(EC.url_contains("/admin/login"))


def test_protected_apis_reject_visitors():
    assert api("/api/customer/dashboard")[0] == 401
    assert api("/api/admin/dashboard")[0] == 401


# ------------------------------------------------------------------ registration
def test_register_new_customer_then_sign_in(browser):
    email = f"ui_{uuid.uuid4().hex[:10]}@example.com"
    browser.get(BASE + "/register")
    wait(browser).until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[type=text]")))
    browser.find_element(By.CSS_SELECTOR, "input[type=text]").send_keys("Selenium Tester")
    browser.find_element(By.CSS_SELECTOR, "input[type=email]").send_keys(email)
    pwds = browser.find_elements(By.CSS_SELECTOR, "input[type=password]")
    pwds[0].send_keys(CUSTOMER_PASSWORD)
    pwds[1].send_keys(CUSTOMER_PASSWORD)
    browser.find_element(By.CSS_SELECTOR, "button[type=submit]").click()
    text_visible(browser, "Account created successfully")
    wait(browser, 15).until(EC.url_contains("/login"))
    fill_login(browser, email, CUSTOMER_PASSWORD)
    wait(browser).until(EC.url_contains("/customer"))


def test_register_rejects_duplicate_email():
    email = new_customer()
    status, body = api("/api/auth/register/customer", {
        "full_name": "Someone Else", "email": email,
        "password": CUSTOMER_PASSWORD, "confirm_password": CUSTOMER_PASSWORD})
    assert status == 409


def test_register_rejects_weak_password():
    status, _ = api("/api/auth/register/customer", {
        "full_name": "Weak Pass", "email": f"w_{uuid.uuid4().hex[:8]}@example.com",
        "password": "password", "confirm_password": "password"})
    assert status == 422


# ------------------------------------------------------------------ customer login / logout / RBAC
def test_customer_login_shows_dashboard_then_sign_out(browser):
    email = new_customer()
    customer_login(browser, email)
    wait(browser).until(EC.url_contains("/customer"))
    text_visible(browser, "Selenium Tester")
    browser.find_element(By.XPATH, "//button[contains(., 'Sign Out')]").click()
    wait(browser).until(EC.url_contains("/login"))
    # after logout the portal is closed again
    browser.get(BASE + "/customer")
    wait(browser).until(EC.url_contains("/login"))


def test_wrong_password_shows_error_and_stays_on_login(browser):
    email = new_customer()
    customer_login(browser, email, "Wrong#Pass1")
    text_visible(browser, "Invalid email or password")
    assert "/customer" not in browser.current_url


def test_unknown_email_gets_generic_error(browser):
    customer_login(browser, f"nobody_{uuid.uuid4().hex[:8]}@example.com", "Wrong#Pass1")
    text_visible(browser, "Invalid email or password")


def test_account_locks_after_five_wrong_passwords(browser):
    email = new_customer()
    for _ in range(5):
        status, _ = api("/api/auth/login", {"email": email, "password": "Wrong#Pass1", "portal_type": "CUSTOMER"})
    assert status == 429
    # even the correct password is refused while locked
    customer_login(browser, email, CUSTOMER_PASSWORD)
    text_visible(browser, "locked")
    assert "/customer" not in browser.current_url


def test_customer_cannot_use_admin_portal(browser):
    email = new_customer()
    browser.get(BASE + "/admin/login")
    fill_login(browser, email, CUSTOMER_PASSWORD)
    text_visible(browser, "does not possess Administrative privileges")
    assert "/admin" in browser.current_url and "/login" in browser.current_url


def test_logged_in_customer_is_sent_away_from_admin_page(browser):
    email = new_customer()
    customer_login(browser, email)
    wait(browser).until(EC.url_contains("/customer"))
    browser.get(BASE + "/admin")                      # session cookie is kept, role is CUSTOMER
    wait(browser).until(EC.url_contains("/customer"))
    assert "/admin" not in browser.current_url


def test_customer_token_cannot_call_admin_api():
    email = new_customer()
    status, body = api("/api/auth/login", {"email": email, "password": CUSTOMER_PASSWORD, "portal_type": "CUSTOMER"})
    assert status == 200
    req = urllib.request.Request(BASE + "/api/admin/dashboard",
                                 headers={"Authorization": f"Bearer {body['access_token']}"})
    with pytest.raises(urllib.error.HTTPError) as err:
        urllib.request.urlopen(req, timeout=15)
    assert err.value.code == 403


# ------------------------------------------------------------------ admin
@needs_admin
def test_admin_login_dashboard_and_sign_out(browser):
    admin_login(browser)
    wait(browser).until(EC.url_contains("/admin"))
    text_visible(browser, "Fraud Monitoring & Access Management")
    browser.find_element(By.XPATH, "//button[contains(., 'Terminate Admin Session')]").click()
    wait(browser).until(EC.url_contains("/admin/login"))


@needs_admin
def test_admin_cannot_use_customer_portal(browser):
    browser.get(BASE + "/login")
    fill_login(browser, ADMIN_EMAIL, ADMIN_PASSWORD)
    text_visible(browser, "Admin Portal")              # "Administrative accounts must use the dedicated Admin Portal."
    assert "/admin" not in browser.current_url.replace("/admin/login", "")


@needs_admin
def test_admin_wrong_password_is_refused(browser):
    browser.get(BASE + "/admin/login")
    fill_login(browser, ADMIN_EMAIL, "Wrong#Pass1")
    text_visible(browser, "Invalid email or password")