import os

from dotenv import load_dotenv

from firebase import get_firestore

load_dotenv()


def main() -> None:
    db = get_firestore()
    docs = list(db.collection("cases").stream())
    updated = 0

    for doc in docs:
        data = doc.to_dict() or {}
        full_name = data.get("full_name")
        passport_data = data.get("passport_data")
        updates = {}

        if full_name and not data.get("full_name_lower"):
            updates["full_name_lower"] = str(full_name).lower()

        if passport_data and not data.get("passport_data_lower"):
            updates["passport_data_lower"] = str(passport_data).lower()

        if updates:
            doc.reference.update(updates)
            updated += 1

    print(f"Updated {updated} documents")


if __name__ == "__main__":
    main()
