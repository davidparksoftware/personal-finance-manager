import pdfplumber
import pandas as pd
from pathlib import Path
import re
from datetime import datetime
from collections import Counter

import logging
import warnings

warnings.filterwarnings("ignore", category=UserWarning)
logging.getLogger("pdfminer").setLevel(logging.ERROR)

BROKEN_WORD_FIXES = {
    "A ccount"  : "Account",
    "C OSTCO"   : "COSTCO",
    "U S"       : "US",
    "3 65"      : "365",
    "I nterest" : "Interest",
    "a ccount"  : "account",
    "M INES"    : "MINES",
    "C hecking" : "Checking",
    "C HIPOTLE" : "CHIPOTLE",
    "C OCA"     : "COCA",
    "J P"       : "JP",
    "K ING"     : "KING",
    "H IGHWAY"  : "HIGHWAY",
    "H IGHLANDS": "HIGHLANDS",
    "B URGER"   : "BURGER",
    "T ACO"     : "TACO",
    "M AVERIK"  : "MAVERIK",
    "S POTIFY"  : "SPOTIFY",
    "S narfs"   : "Snarfs",
    "C ENTER"   : "CENTER",
    "P KWY"     : "PKWY",
    "A venue"   : "Avenue",
    "T hornton" : "Thornton",
    "J IMMY"    : "JIMMY",
    "C HERRY"   : "CHERRY",
    "S T"       : "ST",
    "T ARGET"   : "TARGET",
    "C OLORADO" : "COLORADO",
    "R AISING"  : "RAISING",
    "S HELL"    : "SHELL",
    "P eacock"  : "Peacock",
    "R OCKET"   : "ROCKET",
    "C IRCLE"   : "CIRCLE",
    "L EGO"     : "LEGO",
    "U NITED"   : "UNITED",
    "D D"       : "DD",
    "D icks"    : "Dicks",
    "S tore"    : "Store",
    "L akewood" : "Lakewood",
    "H OLIDAY"  : "HOLIDAY",
    "S NARFS"   : "SNARFS",
    "P ROTON"   : "PROTON",
    "F LYING"   : "FLYING",
    "S avings"  : "Savings",
    "S TARBUCKS": "STARBUCKS",
    "M URPHY"   : "MURPHY",
    "O verdraft": "Overdraft",
    "S ubway"   : "Subway",
    "S AFEWAY"  : "SAFEWAY",
    "C OLFAX"   : "C OLFAX",
    "A ve."     : "Ave.",
    "S treet"   : "Street",
    "G OLDEN"   : "GOLDEN",
    "M ICRO"    : "MICRO",

}

def starts_with_valid_date(line):
    """
        This function checks to see if the line is a new transaction
    """
    parts = line.strip().split()
    if not parts:
        return False
    
    try:
        datetime.strptime(parts[0], "%m/%d/%Y")
        return True
    except ValueError:
        return False


def extract_amounts(line):
    """
        This function extracts the credit and debit amounts from the last 3 items
        Assumes format: <date> <description> $credit -$debit $balance
    """
    parts = line.strip().split()
    if len(parts) < 5:
        return None, None
    
    try:
        credit_str = parts[-3]
        debit_str  = parts[-2]

        credit = float(credit_str.replace("$", "").replace(",", ""))
        debit  = float(debit_str.replace("$", "").replace(",", ""))
        return credit, debit
    except ValueError:
        return None, None


def is_valid_transaction(line):
    credit, debit = extract_amounts(line)
    return starts_with_valid_date(line) and credit is not None and debit is not None


def extract_account_name_number(lines):
    for line in lines[:15]:  # Check top part of page
        if "Account Number:" in line:
            parts = line.split("Account Number:")[1].strip().split()
            if parts:
                return parts[0]
    return None


def clean_description(text):
    return re.sub(r'\s+', ' ', text).strip()


def find_broken_phrases(descriptions):
    broken_phrases = Counter()
    rules_hit = Counter()

    for desc in descriptions:
        words = desc.split()
        for i in range(len(words) - 1):
            w1, w2 = words[i], words[i + 1]
            phrase = f"{w1} {w2}"

            # Case 1: Single-letter capital + lowercase
            if re.match(r'^[A-Z]$', w1) and re.match(r'^[a-z]', w2):
                broken_phrases[phrase] += 1
                rules_hit["single_cap + lowercase"] += 1

            # Case 2a: Capital short + ALLCAPS word
            if re.match(r'^[A-Z]{1,2}$', w1) and re.match(r'^[A-Z]{3,}$', w2):
                broken_phrases[phrase] += 1
                rules_hit["short_cap + ALLCAP"] += 1

            # Case 2b: Capital short + Capitalized word
            if re.match(r'^[A-Z]{1,2}$', w1) and re.match(r'^[A-Z][a-z]+$', w2):
                broken_phrases[phrase] += 1
                rules_hit["short_cap + Capitalized"] += 1

            # Case 3: Digit + digit
            if re.match(r'^\d$', w1) and re.match(r'^\d', w2):
                broken_phrases[phrase] += 1
                rules_hit["digit + digit"] += 1

            # Case 4: lowercase + lowercase
            if re.match(r'^[a-z]', w1) and re.match(r'^[a-z]', w2):
                broken_phrases[phrase] += 1
                rules_hit["lowercase + lowercase"] += 1

            # Case 5: comma + Capitalized
            if w1.endswith(",") and re.match(r'^[A-Z][a-z]+$', w2):
                broken_phrases[phrase] += 1
                rules_hit["word, + Capitalized"] += 1

            # Case 6: Misjoined Abbreviations (e.g. U S)
            if all(len(w) == 1 and w.isupper() for w in [w1, w2]):
                broken_phrases[phrase] += 1
                rules_hit["abbreviation spacing"] += 1

    # Print rule hit summary
    print("\n--- Rule Hit Counts ---")
    for rule, count in rules_hit.most_common():
        print(f"{rule:<25} : {count}x")

    return broken_phrases


def patch_known_broken_phrases(text):
    for broken, fixed in BROKEN_WORD_FIXES.items():
        text = text.replace(broken, fixed)
    return text


def parse_ally_statement(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        current_account_number = "Unknown"
        transactions = []

        for page_num, page in enumerate(pdf.pages, 1):
            text = page.extract_text()
            if not text:
                continue

            current = None

            lines = text.split('\n')
            new_account_number = extract_account_name_number(lines)
            if new_account_number and new_account_number != current_account_number:
                current_account_number = new_account_number

            for line in lines:
                if is_valid_transaction(line):
                    if current:
                        transactions.append(current)
                    
                    parts = line.strip().split()
                    date = parts[0]
                    credit, debit = extract_amounts(line)
                    description = " ".join(parts[1:-3])
                    description = clean_description(description)
                    
                    current = {
                        "Date": date,
                        "Description": description,
                        "Credit": credit,
                        "Debit": debit,
                        "Account_Number": current_account_number,
                        "Source_File": pdf_path.name
                    }
                elif current:
                    if "Ending Balance" in line:
                        continue
                    # Heuristic: avoid appending weird short codes or unrelated lines
                    if re.match(r'^\d{6}/', line):  # Skip known footer pattern
                        continue
                    if len(line.strip()) > 1:
                        current["Description"] += ' ' + line.strip()
                        current["Description"] = clean_description(current["Description"])
                        
            if current:
                transactions.append(current)

        return pd.DataFrame(transactions)


def get_latest_transactions():
    statement_folder = Path("bank_statements")
    output_file = Path("all_transactions.csv")

    all_dfs = []

    for pdf_path in statement_folder.glob("*.pdf"):
        try:
            print(f"Processing {pdf_path.name}...")
            df = parse_ally_statement(pdf_path)
            if not df.empty:
                print(f"    Found {len(df)} transactions in {pdf_path.name}")
                all_dfs.append(df)
        except Exception as e:
            print(f"Error processing {pdf_path.name}: {e}")
    
    if all_dfs:
        full_df = pd.concat(all_dfs, ignore_index=True)

        # Convert the Date column to an actual date
        full_df['Date'] = pd.to_datetime(full_df['Date'])

        # Sort by date then by account number
        full_df = full_df.sort_values(by=['Date', 'Account_Number'])

        full_df.to_csv(output_file, index=False)
        print(f"\nExported {len(full_df)} transactions to {output_file}")
    else:
        print("No transactions found")


def main():
    get_latest_transactions()

    df = pd.read_csv("all_transactions.csv")
    df["Description"] = df["Description"].apply(patch_known_broken_phrases)
    df.to_csv("all_transactions.csv", index=False)


if __name__ == "__main__":
    main()