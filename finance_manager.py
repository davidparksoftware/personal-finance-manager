import pdfplumber
import pandas as pd
from pathlib import Path
import re
from datetime import datetime


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

                    current = {
                        "Date": date,
                        "Description": description,
                        "Credit": credit,
                        "Debit": debit,
                        "Account_Number": current_account_number
                    }
                elif current:
                    if "Ending Balance" in line:
                        continue
                    # Heuristic: avoid appending weird short codes or unrelated lines
                    if re.match(r'^\d{6}/', line):  # Skip known footer pattern
                        continue
                    if len(line.strip()) > 1:
                        current["Description"] += ' ' + line.strip()
            
            if current:
                transactions.append(current)

        return pd.DataFrame(transactions)


def main():
    pdf_file = Path("bank_statements/may_09_2025_statement.pdf")
    output_file = Path("all_transactions.csv")

    df = parse_ally_statement(pdf_file)
    df.to_csv(output_file, index=False)
    print(f"\nExported {len(df)} transactions to {output_file}")


if __name__ == "__main__":
    main()