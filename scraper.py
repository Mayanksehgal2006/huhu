# scraper.py
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import base64
import logging

def launch_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(options=options)

def get_captcha_image(driver):
    driver.get("https://webportal.jiit.ac.in:6011/studentportal/#/login")
    time.sleep(5)
    captcha_img = driver.find_element(By.TAG_NAME, "img")
    src = captcha_img.get_attribute("src")
    if "base64" in src:
        return base64.b64decode(src.split(",")[1])
    return None

def login_and_fetch_attendance(driver, username, password, captcha, semester):
    try:
        driver.find_element(By.ID, "mat-input-0").send_keys(username)
        driver.find_element(By.ID, "mat-input-1").send_keys(password)
        driver.find_element(By.CSS_SELECTOR, "input.ng-pristine").send_keys(captcha)
        driver.find_element(By.CSS_SELECTOR, "button.ng-pristine").click()
        time.sleep(5)

        class_menu = driver.find_element(By.XPATH, "//*[text()='Class and Attendance']")
        driver.execute_script("arguments[0].click();", class_menu)
        time.sleep(1)

        attendance_link = driver.find_element(By.XPATH, "//*[text()='My Class Attendance by Student']")
        driver.execute_script("arguments[0].click();", attendance_link)
        time.sleep(3)

        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "mat-select"))
        ).click()
        time.sleep(1)

        driver.find_element(By.XPATH, f"//*[contains(text(),'{semester}')]").click()
        time.sleep(1)
        driver.find_element(By.XPATH, "//button[contains(text(),'Submit')]").click()
        time.sleep(3)

        table = driver.find_element(By.ID, "pn_id_4-table")
        rows = table.find_elements(By.TAG_NAME, "tr")

        result = "*Your Attendance:*\n"
        for row in rows[1:]:
            cols = row.find_elements(By.TAG_NAME, "td")
            result += f"{cols[1].text}: {cols[5].text}%\n"
        return result

    except Exception as e:
        logging.error(f"Login or scraping failed: {e}")
        return None

