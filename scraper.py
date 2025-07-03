import time
import base64
import json
import tempfile
import os
import shutil
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

CONFIG_PATH = "config.json"

def load_config():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def save_config(data):
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=4)

def launch_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280x1696")

    tmp_profile_dir = tempfile.mkdtemp()
    options.add_argument(f"--user-data-dir={tmp_profile_dir}")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    # Attach temp dir to driver so you can clean it up later
    driver.temp_profile_dir = tmp_profile_dir
    return driver

def fetch_captcha_base64(driver):
    driver.get("https://webportal.jiit.ac.in:6011/studentportal/#/login")
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "img")))
    captcha_img = driver.find_element(By.TAG_NAME, "img")
    src = captcha_img.get_attribute("src")
    if "base64" in src:
        return src.split(",")[1]
    return None

def login_and_fetch_attendance(driver, captcha_text, username, password, semester):
    try:
        driver.find_element(By.ID, "mat-input-0").send_keys(username)
        driver.find_element(By.ID, "mat-input-1").send_keys(password)
        driver.find_element(By.CSS_SELECTOR, "input.ng-pristine").send_keys(captcha_text)
        driver.find_element(By.CSS_SELECTOR, "button.ng-pristine").click()
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//*[text()='Class and Attendance']"))
        ).click()
        time.sleep(1)
        driver.find_element(By.XPATH, "//*[text()='My Class Attendance by Student']").click()
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "mat-select"))
        ).click()
        time.sleep(1)
        driver.find_element(By.XPATH, f"//*[contains(text(),'{semester}')]").click()
        time.sleep(1)
        driver.find_element(By.XPATH, "//button[contains(text(),'Submit')]").click()
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "pn_id_4-table"))
        )

        table = driver.find_element(By.ID, "pn_id_4-table")
        rows = table.find_elements(By.TAG_NAME, "tr")

        attendance = "*Your Attendance:*\n"
        for row in rows[1:]:
            cols = row.find_elements(By.TAG_NAME, "td")
            if len(cols) >= 6:
                subject = cols[1].text
                percent = cols[5].text
                attendance += f"{subject}: {percent}%\n"
        return attendance or "No attendance data found."
    finally:
        # Clean up temporary Chrome profile directory
        if hasattr(driver, "temp_profile_dir"):
            shutil.rmtree(driver.temp_profile_dir, ignore_errors=True)
