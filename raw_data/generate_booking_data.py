import pandas as pd
import random
from datetime import datetime, timedelta

# List of possible room types, currencies, and hotels
room_types = ['first_class_2_bed', 'balcony_2_bed', 'standard_3_bed', 'standard_1_bed', 'standard_2_bed']
currencies = ['GBP', 'EUR']
hotel_ids = [1, 2, 3, 4, 5, 6]
client_ids = [1, 2, 3, 4, 5, 6, 7]

# Function to generate random booking dates
def random_date(start, end):
    delta = end - start
    random_days = random.randint(0, delta.days)
    return start + timedelta(days=random_days)

# Define the range for random dates
start_date = datetime.strptime('01-01-2016', '%d-%m-%Y')
end_date = datetime.strptime('31-12-2023', '%d-%m-%Y')

# List to store the random records
records = []

# Generate 50 random records
for _ in range(50):
    client_id = random.choice(client_ids)
    booking_date = random_date(start_date, end_date).strftime('%d-%m-%Y')
    room_type = random.choice(room_types)
    hotel_id = random.choice(hotel_ids)
    booking_cost = round(random.uniform(1500, 5000), 2)
    currency = random.choice(currencies)
    booking_cost = round(random.uniform(1500, 5000))  # Remove decimal places
    record = {
        'client_id': client_id,
        'booking_date': booking_date,
        'room_type': room_type,
        'hotel_id': hotel_id,
        'booking_cost': booking_cost,
        'currency': currency
    }
    records.append(record)

# Convert the records to a pandas DataFrame
df = pd.DataFrame(records)

# Define file path
file_path = '/home/hanif/Airflow_Pyspark/raw_data/random_booking_data.csv'


# Write DataFrame to CSV with tab separator
df.to_csv(file_path, sep='\t', index=False, header=True, quoting=0) 

# Read the file and add quotes around each line
# with open(file_path, 'r') as file:
#     lines = file.readlines()

# with open(file_path, 'w') as file:
#     for line in lines:
#         file.write(f'"{line.strip()}"\n')

print(df.head())  # Display the first few rows
