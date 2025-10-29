# import os
# import time
# from selenium import webdriver
# from selenium.webdriver.common.by import By
# from selenium.webdriver.common.keys import Keys
#
# # Try installing missing modules
# try:
#     from webdriver_manager.chrome import ChromeDriverManager
# except ModuleNotFoundError:
#     os.system("pip install webdriver-manager")
#     from webdriver_manager.chrome import ChromeDriverManager
#
# from selenium.webdriver.chrome.service import Service
# from selenium.webdriver.chrome.options import Options
#
# # Setup Chrome options
# chrome_options = Options()
# chrome_options.add_argument("--headless")  # Run in headless mode (no UI)
# chrome_options.add_argument("--no-sandbox")
# chrome_options.add_argument("--disable-dev-shm-usage")
#
# # Setup WebDriver
# try:
#     service = Service(ChromeDriverManager().install())
#     driver = webdriver.Chrome(service=service, options=chrome_options)
# except Exception as e:
#     print(f"Error initializing WebDriver: {e}")
#     exit(1)
#
# # Open Khamsat login page
# driver.get("https://accounts.hsoub.com/login?source=khamsat&locale=ar")
#
# # Wait for page to load
# time.sleep(5)
#
# # Try logging in
# try:
#     email_input = driver.find_element(By.NAME, "email")
#     email_input.send_keys("qozeemmonsurudeen@gmail.com")  # Change this
#
#     password_input = driver.find_element(By.NAME, "password")
#     password_input.send_keys("horlas082001")  # Change this
#     password_input.send_keys(Keys.RETURN)
#
#     print("Login attempted successfully!")
#
# except Exception as e:
#     print(f"Error during login: {e}")
#
# # Wait to observe login before closing
# time.sleep(10)
#
# # Close the browser
# driver.quit()