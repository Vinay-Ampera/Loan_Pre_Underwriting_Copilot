"""Invented Indian identities with valid PAN / Aadhaar / GSTIN / Udyam formats.

Every name, city, employer and bank here is made up. Numbers pass format and checksum rules
only; they are not issued to anyone. `gender` is kept for the isolated fairness table and is
never printed on a document the pipeline reads.
"""

import random
import string
from dataclasses import dataclass, field
from datetime import date

from app.intake.validators import gstin_check_char, verhoeff_check_digit

MALE = ["Arjun", "Rohan", "Vikram", "Karthik", "Suresh", "Anil", "Manoj", "Rahul", "Sanjay",
        "Deepak", "Naveen", "Prakash", "Ramesh", "Imran", "Faizan", "Harish", "Gopal", "Mohan",
        "Ashok", "Nitin", "Varun", "Sandeep", "Kiran", "Pavan", "Arvind"]  # fmt: skip
FEMALE = ["Priya", "Anjali", "Sneha", "Kavya", "Divya", "Meera", "Lakshmi", "Pooja", "Neha",
          "Swati", "Radha", "Sunita", "Fatima", "Ayesha", "Shruti", "Geeta", "Nisha", "Rekha",
          "Aparna", "Deepa", "Latha", "Jyoti", "Manasa", "Bhavna", "Tanvi"]  # fmt: skip
SURNAMES = ["Sharma", "Reddy", "Iyer", "Nair", "Patel", "Gupta", "Kulkarni", "Menon", "Banerjee",
            "Das", "Singh", "Khan", "Joshi", "Rao", "Naidu", "Chowdhury", "Mehta", "Pillai",
            "Verma", "Yadav", "Kapoor", "Bhat", "Hegde", "Shetty", "Mishra", "Pandey", "Thakur",
            "Saxena", "Agarwal", "Malhotra", "Desai", "Kamath", "Varma", "Ghosh", "Sinha"]  # fmt: skip

# city, state code (GST), state name, tier
CITIES = [
    ("Mumbai", "27", "Maharashtra", 1), ("Delhi", "07", "Delhi", 1),
    ("Bengaluru", "29", "Karnataka", 1), ("Hyderabad", "36", "Telangana", 1),
    ("Chennai", "33", "Tamil Nadu", 1), ("Pune", "27", "Maharashtra", 2),
    ("Ahmedabad", "24", "Gujarat", 2), ("Jaipur", "08", "Rajasthan", 2),
    ("Lucknow", "09", "Uttar Pradesh", 2), ("Kochi", "32", "Kerala", 2),
    ("Indore", "23", "Madhya Pradesh", 3), ("Nagpur", "27", "Maharashtra", 3),
    ("Coimbatore", "33", "Tamil Nadu", 3), ("Vijayawada", "37", "Andhra Pradesh", 3),
    ("Mysuru", "29", "Karnataka", 3),
]  # fmt: skip
STATE_CODE_LETTERS = {"27": "MH", "07": "DL", "29": "KA", "36": "TS", "33": "TN", "24": "GJ",
                      "08": "RJ", "09": "UP", "32": "KL", "23": "MP", "37": "AP"}  # fmt: skip
STREETS = ["MG Road", "Gandhi Nagar", "Lake View Road", "Temple Street", "Park Avenue",
           "Station Road", "Hill Colony", "Rose Garden Lane", "Market Cross Road", "Green Park"]  # fmt: skip

EMPLOYERS = ["Bluepeak Software Pvt Ltd", "Orchid Textiles Ltd", "Zenith Logistics Pvt Ltd",
             "Maple Health Services", "Riverbend Infra Ltd", "Kestrel Analytics Pvt Ltd",
             "Sunrise Motors Pvt Ltd", "Lotus Pharma Ltd", "Northwind Retail Pvt Ltd",
             "Cobalt Engineering Works", "Silverline Telecom Ltd", "Harbor Foods Pvt Ltd",
             "Pinnacle Education Trust", "Meridian Hospitality Ltd", "Aster Power Systems"]  # fmt: skip
DESIGNATIONS = ["Senior Executive", "Assistant Manager", "Software Engineer", "Team Lead",
                "Accounts Officer", "Operations Manager", "Sales Manager", "Technician"]  # fmt: skip
BUSINESS_KINDS = [("Traders", "wholesale trading"), ("Fabricators", "metal fabrication"),
                  ("Foods", "food processing"), ("Agencies", "distribution"),
                  ("Printers", "printing"), ("Electricals", "electrical contracting")]  # fmt: skip
CONSTITUTIONS = ["Proprietorship", "Partnership", "Private Limited"]

INSTITUTIONS_IN = ["Western Ridge Institute of Technology", "Coastal University of Management",
                   "Deccan College of Engineering", "Heritage Medical College"]  # fmt: skip
INSTITUTIONS_ABROAD = [("Northfield University", "Canada"), ("Lakeshore Institute", "UK"),
                       ("Pacific Tech University", "USA")]  # fmt: skip
VEHICLES = {
    "new_car": [("Veloce", "Sprint 1.2"), ("Rhino", "Trail 1.5"), ("Aria", "Metro 1.0")],
    "used_car": [("Veloce", "Sprint 1.2"), ("Aria", "Metro 1.0")],
    "two_wheeler": [("Zippy", "Commuter 110"), ("Stallion", "Cruiser 350")],
}  # fmt: skip
DEALERS = ["Star Motors", "City Wheels", "Prime Autos", "Highway Motors"]
COLLEGES_BOARD = ["State Secondary Board", "Central Higher Secondary Board"]


@dataclass
class Person:
    role: str  # primary | co
    first: str
    surname: str
    gender: str
    dob: date
    pan: str
    aadhaar: str
    city: str
    state_code: str
    state: str
    tier: int
    address: str
    phone: str
    employment_type: str  # salaried | self_employed | student
    employer: str = ""
    designation: str = ""
    father_first: str = ""
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def full_name(self) -> str:
        return f"{self.first} {self.surname}"

    @property
    def aadhaar_last4(self) -> str:
        return self.aadhaar[-4:]

    @property
    def aadhaar_spaced(self) -> str:
        a = self.aadhaar
        return f"{a[:4]} {a[4:8]} {a[8:]}"


class IdFactory:
    """Hands out unique PAN / Aadhaar / phone values for one generation run."""

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self._pans: set[str] = set()
        self._aadhaars: set[str] = set()

    def pan(self, surname: str, holder: str = "P") -> str:
        while True:
            pan = (
                "".join(self.rng.choices(string.ascii_uppercase, k=3))
                + holder
                + surname[0].upper()
                + f"{self.rng.randint(0, 9999):04d}"
                + self.rng.choice(string.ascii_uppercase)
            )
            if pan not in self._pans:
                self._pans.add(pan)
                return pan

    def aadhaar(self) -> str:
        while True:
            payload = str(self.rng.randint(2, 9)) + "".join(self.rng.choices(string.digits, k=10))
            number = payload + verhoeff_check_digit(payload)
            if number not in self._aadhaars:
                self._aadhaars.add(number)
                return number

    def phone(self) -> str:
        return str(self.rng.randint(6, 9)) + "".join(self.rng.choices(string.digits, k=9))


def make_person(
    rng: random.Random, ids: IdFactory, role: str, age: int, employment_type: str,
    today: date, surname: str | None = None, gender: str | None = None,
    city: tuple[str, str, str, int] | None = None,
) -> Person:  # fmt: skip
    gender = gender or rng.choice(["M", "F"])
    first = rng.choice(MALE if gender == "M" else FEMALE)
    surname = surname or rng.choice(SURNAMES)
    c = city or rng.choice(CITIES)
    dob = date(
        today.year - age - (0 if rng.random() < 0.5 else 1), rng.randint(1, 12), rng.randint(1, 28)
    )
    # make the stated age true as of `today`
    while _age(dob, today) != age:
        dob = date(dob.year + (1 if _age(dob, today) > age else -1), dob.month, dob.day)
    house = rng.randint(1, 480)
    address = f"{house}, {rng.choice(STREETS)}, {c[0]}, {c[2]} {rng.randint(100000, 899999)}"
    return Person(
        role=role, first=first, surname=surname, gender=gender, dob=dob,
        pan=ids.pan(surname), aadhaar=ids.aadhaar(), city=c[0], state_code=c[1], state=c[2],
        tier=c[3], address=address, phone=ids.phone(), employment_type=employment_type,
        employer=rng.choice(EMPLOYERS) if employment_type == "salaried" else "",
        designation=rng.choice(DESIGNATIONS) if employment_type == "salaried" else "",
        father_first=rng.choice(MALE),
    )  # fmt: skip


def _age(dob: date, on: date) -> int:
    return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))


def age_on(dob: date, on: date) -> int:
    return _age(dob, on)


def make_gstin(rng: random.Random, state_code: str, pan: str) -> str:
    first14 = f"{state_code}{pan}{rng.randint(1, 9)}Z"
    return first14 + gstin_check_char(first14)


def make_udyam(rng: random.Random, state_code: str) -> str:
    return f"UDYAM-{STATE_CODE_LETTERS[state_code]}-{rng.randint(1, 40):02d}-{rng.randint(0, 9999999):07d}"
