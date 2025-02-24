import base64
import os
import random
import string
import requests
from curl_cffi import requests as curl_requests
from datetime import datetime, timezone
from fake_useragent import UserAgent
from twocaptcha import TwoCaptcha
from anticaptchaofficial.imagecaptcha import *
from dotenv import load_dotenv
import os

load_dotenv()

ua = UserAgent()

model = None
MAX_RETRIES = 10

def get_headers(token=None):
    headers = {
        'accept': '/',
        'accept-language': 'en-US,en;q=0.9',
        'origin': 'chrome-extension://fpdkjdnhkakefebpekbdhillbhonfjjp',
        'priority': 'u=1, i',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'cross-site',
        'user-agent': ua.chrome
    }
    if token:
        headers['Authorization'] = f'Bearer {token}'
    return headers

def setup_captcha_solver(api_key, solver_type):
    global solver, model
    model = solver_type
    
    if solver_type == "2captcha":
        solver = TwoCaptcha(api_key)
    else:
        solver = imagecaptcha()
        solver.set_key(api_key)
    return solver

def get_puzzle_id(app_id, proxies):
    url = 'https://www.aeropres.in/chromeapi/dawn/v1/puzzle/get-puzzle'
    params = {
        'appid': app_id
    }
    
    retry_count = 0
    while retry_count < MAX_RETRIES:
        try:
            response = curl_requests.get(
                url, 
                headers=get_headers(),
                params=params,
                proxies=proxies,
                impersonate="chrome110",
                timeout=120
            )
            response.raise_for_status()
            return response.json()['puzzle_id']
        except Exception as e:
            retry_count += 1
            if retry_count < MAX_RETRIES:
                print(f"Connection error getting puzzle ID: {str(e)}. Retrying... ({retry_count}/{MAX_RETRIES})")
            else:
                print(f"Error getting puzzle ID after {MAX_RETRIES} attempts: {str(e)}")
                raise

def get_puzzle_image(puzzle_id, app_id, proxies):
    url = 'https://www.aeropres.in/chromeapi/dawn/v1/puzzle/get-puzzle-image'
    params = {
        'puzzle_id': puzzle_id,
        'appid': app_id
    }
    
    retry_count = 0
    while retry_count < MAX_RETRIES:
        try:
            response = curl_requests.get(
                url, 
                headers=get_headers(),
                params=params,
                proxies=proxies,
                impersonate="chrome110",
                timeout=120
            )
            response.raise_for_status()
            return response.json()['imgBase64']
        except Exception as e:
            retry_count += 1
            if retry_count < MAX_RETRIES:
                print(f"Connection error getting puzzle image: {str(e)}. Retrying... ({retry_count}/{MAX_RETRIES})")
            else:
                print(f"Error getting puzzle image after {MAX_RETRIES} attempts: {str(e)}")
                raise

def process_image(base64_image, solver_type):
    try:
        image_data = base64.b64decode(base64_image)
        temp_image = "temp_captcha.png"
        
        with open(temp_image, "wb") as f:
            f.write(image_data)

        try:
            if solver_type == "2captcha":
                result = solver.normal(temp_image)
                captcha_text = result['code']
            else:
                solver.set_verbose(0)
                captcha_text = solver.solve_and_return_solution(file_path=temp_image)
                if captcha_text == 0:
                    raise Exception("Failed to solve captcha")
            
            return captcha_text
            
        finally:
            if os.path.exists(temp_image):
                os.remove(temp_image)
                
    except Exception as e:
        print(f"Error solving captcha: {str(e)}")
        raise

def login_user(email, password, app_id, proxies):
    print("Attempting to login...")
    retry_count = 0
    
    while retry_count < MAX_RETRIES:
        try:
            login_successful = False
            while not login_successful:
                puzzle_id = get_puzzle_id(app_id, proxies)
                print(f"Login Captcha ID: {puzzle_id}")
                
                image_base64 = get_puzzle_image(puzzle_id, app_id, proxies)
                captcha_text = process_image(image_base64, model)
                print(f"Solved Login Captcha: {captcha_text}")
                
                current_datetime = datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
                
                login_data = {
                    "username": email,
                    "password": password,
                    "logindata": {
                        "_v": {"version": "1.1.2"},
                        "datetime": current_datetime
                    },
                    "puzzle_id": puzzle_id,
                    "ans": captcha_text
                }
                
                headers = get_headers()
                headers['content-type'] = 'application/json'
                
                response = curl_requests.post(
                    f'https://www.aeropres.in/chromeapi/dawn/v1/user/login/v2',
                    params={'appid': app_id},
                    headers=headers,
                    json=login_data,
                    proxies=proxies,
                    impersonate="chrome110",
                    timeout=120
                )
                
                if response.status_code == 200:
                    print("Login successful!")
                    login_successful = True
                    return response.json()
                elif response.status_code == 400:
                    print("Invalid CAPTCHA, retrying with new captcha...")
                    continue
                else:
                    print(f"Login failed with status {response.status_code}, retrying...")
                    retry_count += 1
                    break
                    
        except Exception as e:
            retry_count += 1
            if retry_count < MAX_RETRIES:
                print(f"Login error: {str(e)}. Retrying... ({retry_count}/{MAX_RETRIES})")
            else:
                print(f"Login failed after {MAX_RETRIES} attempts: {str(e)}")
                return None
    
    return None

def read_emails_file(file_path):
    if not os.path.exists(file_path):
        print(f"File {file_path} not found.")
        return []
    
    with open(file_path, 'r') as file:
        lines = file.readlines()
    
    email_appid_pairs = []
    for line in lines:
        line = line.strip()
        if line:
            try:
                email, app_id = line.split(',')
                email_appid_pairs.append((email.strip(), app_id.strip()))
            except ValueError:
                print(f"Skipping invalid line: {line}")
    
    return email_appid_pairs

def write_to_json(output_file, data):
    with open(output_file, 'w') as file:
        json.dump(data, file, indent=4)
    print(f"Data written to {output_file}")

def read_proxies_file(file_path):
    # Function to read proxies from proxy.txt
    proxies_list = []
    try:
        with open(file_path, 'r') as file:
            for line in file:
                proxies_list.append(line.strip())
    except FileNotFoundError:
        print(f"File {file_path} not found.")
    return proxies_list

def main():
    solver_type = "2captcha"
    captcha_api_key = os.getenv('2captcha_api')
    setup_captcha_solver(captcha_api_key, solver_type)

    password = os.getenv('password')

    # Read email and app ID pairs from emails.txt
    email_appid_pairs = read_emails_file("emails.txt")
    if not email_appid_pairs:
        print("No valid email and app ID pairs found in emails.txt.")
        return
    

    proxies_list = read_proxies_file("proxy.txt")
    if not proxies_list:
        print("No proxies found in proxy.txt.")
        return

    accounts_data = []
    for i, (email, app_id) in enumerate(email_appid_pairs):
        if i >= len(proxies_list):
            print("Not enough proxies for all accounts.")
            break

        proxy = proxies_list[i]
        proxies = {
            "http": proxy,
            "https": proxy
        }

        print(f"\nProcessing email: {email}, app ID: {app_id}, using proxy: {proxy}")
        login_response = login_user(email, password, app_id, proxies)
        if login_response:
            token = login_response['data']['token']
            print(f"Login successful! Token: {token}")
            accounts_data.append({
                "Email": email,
                "Token": token,
            })
        else:
            print("Login failed.")
    write_to_json("accounts.json", accounts_data)

if __name__ == "__main__":
    main()

