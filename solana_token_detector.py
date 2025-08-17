#!/usr/bin/env python3
"""
Solana Token Detector - Interactive Terminal Application
-------------------------------------------------------

An enhanced version of the Solana token monitoring bot with:
- Beautiful ASCII art header
- Interactive menu system
- Real-time monitoring
- Historical data viewing
- Configurable risk thresholds
"""

import json
import os
import signal
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Set, Optional
import requests
import keyboard
import msvcrt

# Simple Text Header - Guaranteed to work in all terminals
ASCII_ART = """
\033[94m
+--------------------------------------------------------------------------------+
|                                                                                |
|                           SOLANA TOKEN DETECTOR                                |
|                                                                                |
+--------------------------------------------------------------------------------+
\033[0m
\033[93m🚀 Real-time token detection with rug-pull risk analysis\033[0m
"""

# Configuration file
CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {
    "score_threshold": 81,
    "polling_interval": 30,
    "api_timeout": 30
}

# API endpoints
BASE_URL = "https://api.rugcheck.xyz/v1"
NEW_TOKENS_ENDPOINT = f"{BASE_URL}/stats/new_tokens"
SUMMARY_ENDPOINT_TEMPLATE = f"{BASE_URL}/tokens/{{mint}}/report/summary"

# Timezone for Lagos (UTC+1)
LAGOS_TZ = timezone(timedelta(hours=1))

# Filenames for persistent storage
SAFE_TO_BUY_FILE = os.path.join(os.path.dirname(__file__), "safe_to_buy.json")

def clear_screen():
    """Clear the terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')

def print_header():
    """Print the ASCII art header."""
    clear_screen()
    print(ASCII_ART)
    print()

def load_config() -> Dict:
    """Load configuration from file."""
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return DEFAULT_CONFIG

def save_config(config: Dict) -> None:
    """Save configuration to file."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

def load_json(file_path: str) -> List[Dict]:
    """Load a list of dictionaries from a JSON file."""
    if not os.path.exists(file_path):
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

def save_json(file_path: str, data: List[Dict]) -> None:
    """Save a list of dictionaries to a JSON file."""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def fetch_new_tokens() -> List[Dict]:
    """Fetch a list of newly minted tokens from RugCheck."""
    try:
        response = requests.get(NEW_TOKENS_ENDPOINT, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        print(f"⚠️  Error fetching new tokens: {exc}")
        return []

def fetch_token_summary(mint: str) -> Dict:
    """Fetch a summary report for a token mint."""
    url = SUMMARY_ENDPOINT_TEMPLATE.format(mint=mint)
    try:
        res = requests.get(url, timeout=30)
        if res.status_code == 200:
            return res.json()
        else:
            return {}
    except requests.RequestException:
        return {}

def classify_risk(score_normalised: int | None, threshold: int) -> str:
    """Classify risk based on configurable threshold."""
    if score_normalised is None:
        return "UNKNOWN"
    if score_normalised > threshold:
        return "LOW"
    if score_normalised >= 50:
        return "MEDIUM"
    return "HIGH"

def format_report(token: Dict, summary: Dict, detected_at: str, threshold: int) -> str:
    """Format a console report for a detected token."""
    mint = token.get("mint", "Unknown")
    symbol = token.get("symbol") or summary.get("tokenMeta", {}).get("symbol", "")
    name = summary.get("tokenMeta", {}).get("name", symbol or "Unknown Token")
    creator = token.get("creator") or summary.get("creator", "Unknown")
    score_norm = summary.get("score_normalised")
    score_display = score_norm if score_norm is not None else "N/A"
    risk = classify_risk(score_norm, threshold)
    
    recommendation = {
        "LOW": "SAFE_TO_BUY",
        "MEDIUM": "CAUTION_ADVISED",
        "HIGH": "HIGH_RISK_DONT_BUY",
        "UNKNOWN": "CAUTION_ADVISED",
    }[risk]
    
    lines = []
    lines.append("=" * 80)
    lines.append("🚀 NEW TOKEN DETECTED!")
    lines.append("=" * 80)
    lines.append("")
    lines.append("📋 TOKEN INFORMATION:")
    lines.append(f"✅ Token Name: {name}")
    lines.append(f"✅ Token Symbol: {symbol}")
    lines.append(f"✅ Token Mint: {mint}")
    lines.append(f"👤 Creator Wallet: {creator}")
    lines.append(f"🕒 Detection Time: {detected_at}")
    lines.append("")
    lines.append("📊 RUGCHECK ANALYSIS:")
    lines.append(f"- Safety Score: {score_display}/100")
    lines.append(f"- Risk Level: {risk}")
    lines.append(f"- Recommendation: {recommendation}")
    
    risks_list = summary.get("risks") or []
    if risks_list:
        lines.append("- Risk Reasons:")
        for risk_item in risks_list:
            name = risk_item.get("name", "Unknown Risk")
            desc = risk_item.get("description", "")
            level = risk_item.get("level", "")
            lines.append(f"    • {name} ({level}) - {desc}")
    
    return "\n".join(lines)

def append_if_not_exists(file_path: str, entry: Dict) -> None:
    """Append a token entry to a JSON file if it's not already present."""
    existing = load_json(file_path)
    mints = {item.get("mint") for item in existing if isinstance(item, dict)}
    if entry.get("mint") not in mints:
        existing.append(entry)
        save_json(file_path, existing)

def start_monitoring():
    """Start real-time token monitoring."""
    config = load_config()
    threshold = config["score_threshold"]
    interval = config["polling_interval"]
    
    print(f"\n🔍 Starting monitoring with threshold: {threshold}+")
    print(f"⏱️  Polling interval: {interval} seconds")
    print("Press Ctrl+C to stop monitoring\n")
    
    processed: Set[str] = set()
    
    try:
        while True:
            tokens = fetch_new_tokens()
            now_str = datetime.now(LAGOS_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
            
            for token in tokens:
                mint = token.get("mint")
                if not mint or mint in processed:
                    continue
                    
                summary = fetch_token_summary(mint)
                if not summary:
                    processed.add(mint)
                    continue
                
                processed.add(mint)
                score_norm = summary.get("score_normalised")
                risk = classify_risk(score_norm, threshold)
                
                # Debug logging
                print(f"🔍 DEBUG: Token {token.get('symbol', 'Unknown')} - Score: {score_norm}, Threshold: {threshold}, Risk: {risk}")
                
                entry = {
                    "mint": mint,
                    "name": summary.get("tokenMeta", {}).get("name", ""),
                    "symbol": token.get("symbol") or summary.get("tokenMeta", {}).get("symbol", ""),
                    "creator": token.get("creator") or summary.get("creator", ""),
                    "score_normalised": score_norm,
                    "risk": risk,
                    "risks": summary.get("risks", []),
                    "detected_at": now_str,
                }
                
                if risk == "LOW":
                    print(f"✅ SAVING: Token {token.get('symbol', 'Unknown')} with score {score_norm} (>{threshold})")
                    append_if_not_exists(SAFE_TO_BUY_FILE, entry)
                else:
                    print(f"❌ NOT SAVING: Token {token.get('symbol', 'Unknown')} with score {score_norm} (risk: {risk})")
                
                report = format_report(token, summary, now_str, threshold)
                print(report)
                print("\n")
            
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print("\n🛑 Monitoring stopped.")
        print("\n💝 If you loved this tool, feel free to donate to:")
        print("   FnqoYxGvhzJdiKvw5e8MGT2sL5V69XCTSCqA7uU4WX7v")
        input("Press Enter to continue...")

def view_historical_data():
    """View all stored tokens from safe_to_buy.json."""
    tokens = load_json(SAFE_TO_BUY_FILE)
    
    if not tokens:
        print("\n📭 No tokens found in safe_to_buy.json")
        input("Press Enter to continue...")
        return
    
    print(f"\n📊 Historical Data - {len(tokens)} tokens found")
    print("=" * 80)
    
    for i, token in enumerate(tokens, 1):
        print(f"\n{i}. Token: {token.get('symbol', 'Unknown')}")
        print(f"   Name: {token.get('name', 'Unknown')}")
        print(f"   Mint: {token.get('mint', 'Unknown')}")
        print(f"   Score: {token.get('score_normalised', 'N/A')}/100")
        print(f"   Risk: {token.get('risk', 'Unknown')}")
        print(f"   Detected: {token.get('detected_at', 'Unknown')}")
        print(f"   Creator: {token.get('creator', 'Unknown')}")
        
        risks = token.get('risks', [])
        if risks:
            print("   Risk Factors:")
            for risk in risks:
                print(f"     • {risk.get('name', 'Unknown')} ({risk.get('level', 'Unknown')})")
    
    print(f"\n📈 Total tokens stored: {len(tokens)}")
    input("Press Enter to continue...")

def show_configuration():
    """Show current configuration."""
    config = load_config()
    
    print("\n⚙️  Current Configuration")
    print("=" * 40)
    print(f"Score Threshold: {config['score_threshold']}+ (tokens must score above this)")
    print(f"Polling Interval: {config['polling_interval']} seconds")
    print(f"API Timeout: {config['api_timeout']} seconds")
    
    print("\n📋 Risk Classification:")
    print(f"• LOW (Safe): Score > {config['score_threshold']}")
    print(f"• MEDIUM (Warning): 50 ≤ Score ≤ {config['score_threshold']}")
    print(f"• HIGH (Danger): Score < 50")
    
    input("\nPress Enter to continue...")

def edit_configuration():
    """Edit configuration settings."""
    config = load_config()
    
    while True:
        print("\n🔧 Edit Configuration")
        print("=" * 30)
        print(f"1. Score Threshold (current: {config['score_threshold']}+)")
        print(f"2. Polling Interval (current: {config['polling_interval']}s)")
        print(f"3. API Timeout (current: {config['api_timeout']}s)")
        print("4. Back to main menu")
        
        choice = input("\nSelect option (1-4): ").strip()
        
        if choice == "1":
            try:
                new_threshold = int(input(f"Enter new threshold (current: {config['score_threshold']}): "))
                if 1 <= new_threshold <= 100:
                    config['score_threshold'] = new_threshold
                    save_config(config)
                    print(f"✅ Threshold updated to {new_threshold}+")
                else:
                    print("❌ Threshold must be between 1 and 100")
            except ValueError:
                print("❌ Please enter a valid number")
                
        elif choice == "2":
            try:
                new_interval = int(input(f"Enter new polling interval in seconds (current: {config['polling_interval']}): "))
                if 5 <= new_interval <= 300:
                    config['polling_interval'] = new_interval
                    save_config(config)
                    print(f"✅ Polling interval updated to {new_interval} seconds")
                else:
                    print("❌ Interval must be between 5 and 300 seconds")
            except ValueError:
                print("❌ Please enter a valid number")
                
        elif choice == "3":
            try:
                new_timeout = int(input(f"Enter new API timeout in seconds (current: {config['api_timeout']}): "))
                if 10 <= new_timeout <= 120:
                    config['api_timeout'] = new_timeout
                    save_config(config)
                    print(f"✅ API timeout updated to {new_timeout} seconds")
                else:
                    print("❌ Timeout must be between 10 and 120 seconds")
            except ValueError:
                print("❌ Please enter a valid number")
                
        elif choice == "4":
            break
        else:
            print("❌ Invalid option. Please select 1-4.")
        
        input("Press Enter to continue...")

def get_arrow_key_input():
    """Get arrow key input for menu navigation."""
    try:
        while True:
            if msvcrt.kbhit():
                key = msvcrt.getch()
                if key == b'H':  # Up arrow
                    return 'up'
                elif key == b'P':  # Down arrow
                    return 'down'
                elif key == b'\r':  # Enter
                    return 'enter'
                elif key == b'3':  # Escape
                    return 'escape'
    except:
        return None

def display_menu(selected_option: int):
    """Display the menu with proper highlighting."""
    print("\033[92m? What would you like to do?\033[0m \033[90m(Use arrow keys or type number)\033[0m")
    print()
    
    options = [
        "🚀 Start Real-time Monitoring",
        "📊 View Historical Data", 
        "⚙️ Configuration",
        "❌ Exit"
    ]
    
    for i, option in enumerate(options):
        if i == selected_option:
            print(f"\033[94m>\033[0m {option}")
        else:
            print(f"  {option}")
    print()

def main_menu():
    """Display and handle the main menu with arrow key navigation."""
    selected = 0
    
    while True:
        print_header()
        display_menu(selected)
        
        print("Use ↑↓ arrow keys to navigate, Enter to select, or type 1-4")
        print("Enter your choice: ", end="", flush=True)
        
        # Check for arrow key input
        arrow_input = get_arrow_key_input()
        
        if arrow_input == 'up':
            selected = (selected - 1) % 4
            continue
        elif arrow_input == 'down':
            selected = (selected + 1) % 4
            continue
        elif arrow_input == 'enter':
            # Process the selected option
            if selected == 0:
                start_monitoring()
            elif selected == 1:
                view_historical_data()
            elif selected == 2:
                config_menu()
            elif selected == 3:
                print("\n👋 Goodbye!")
                print('{"service":"solana-token-detector"}')
                break
            continue
        
        # Fallback to number input
        try:
            choice = input().strip()
            if choice == "1" or choice.lower() == "start":
                start_monitoring()
            elif choice == "2" or choice.lower() == "historical":
                view_historical_data()
            elif choice == "3" or choice.lower() == "config":
                config_menu()
            elif choice == "4" or choice.lower() == "exit":
                print("\n👋 Goodbye!")
                print('{"service":"solana-token-detector"}')
                break
            else:
                print("❌ Invalid choice. Please select 1-4 or use arrow keys.")
                input("Press Enter to continue...")
        except (EOFError, KeyboardInterrupt):
            print("\n\n👋 Goodbye!")
            print('{"service":"solana-token-detector"}')
            break

def config_menu():
    """Display and handle the configuration menu with arrow key navigation."""
    selected = 0
    
    while True:
        print_header()
        print("\033[92m? Configuration Options\033[0m")
        print()
        
        options = [
            "📋 View Current Configuration",
            "🔧 Edit Configuration", 
            "↩️ Back to Main Menu"
        ]
        
        for i, option in enumerate(options):
            if i == selected:
                print(f"\033[94m>\033[0m {option}")
            else:
                print(f"  {option}")
        print()
        
        print("Use ↑↓ arrow keys to navigate, Enter to select, or type 1-3")
        print("Enter your choice: ", end="", flush=True)
        
        # Check for arrow key input
        arrow_input = get_arrow_key_input()
        
        if arrow_input == 'up':
            selected = (selected - 1) % 3
            continue
        elif arrow_input == 'down':
            selected = (selected + 1) % 3
            continue
        elif arrow_input == 'enter':
            # Process the selected option
            if selected == 0:
                show_configuration()
            elif selected == 1:
                edit_configuration()
            elif selected == 2:
                break
            continue
        
        # Fallback to number input
        try:
            choice = input().strip()
            if choice == "1":
                show_configuration()
            elif choice == "2":
                edit_configuration()
            elif choice == "3":
                break
            else:
                print("❌ Invalid choice. Please select 1-3 or use arrow keys.")
                input("Press Enter to continue...")
        except (EOFError, KeyboardInterrupt):
            break

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
        print('{"service":"solana-token-detector"}')
        sys.exit(0)
