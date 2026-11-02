
import pandas as pd

GCC = [
    "Bahrain", "Kuwait", "Oman",
    "Qatar", "Saudi Arabia", "United Arab Emirates"
]

# Countries to read: the six GCC sheets plus the fallback table
COUNTRIES = GCC + ["Other Countries and Territories"]

SHEET_NAMES = {
    "Other Countries and Territories": "_Other Countries and Territorie",
}

default_file = "data/defaults.xlsx"
rows = []

for country in COUNTRIES:

    sheet = SHEET_NAMES.get(country, country)

    # Include column 5 for the production route
    df = pd.read_excel(
        default_file,
        sheet_name=sheet,
        header=None,
        skiprows=3,
        usecols=[0, 1, 4, 5]
    )

    df.columns = [
        'cn_code',
        'description',
        'total',
        'production_process_route'
    ]
    df['country'] = country

    # Keep rows with numeric CN codes
    df = df[
        df['cn_code'].astype(str).str.match(r'^\d', na=False)
    ].copy()

    # Clean CN codes
    df['cn_code'] = (
        df['cn_code'].astype(str).str.replace(' ', '', regex=False)
    )

    # Convert total emissions to numeric values
    df['total'] = pd.to_numeric(
        df['total'].astype(str).str.replace(',', '.', regex=False),
        errors='coerce'
    )

    # Keep rows with available total emissions
    df = df[df['total'].notna()].copy()

    # Clean production route
    df['production_process_route'] = (
        df['production_process_route']
        .fillna('')
        .astype(str)
        .str.strip()
    )

    # Assign sectors
    df['sector'] = 'Other'

    df.loc[
        df['cn_code'].str.startswith(('26', '72', '73')),
        'sector'
    ] = 'Iron & Steel'

    df.loc[
        df['cn_code'].str.startswith('76'),
        'sector'
    ] = 'Aluminium'

    df.loc[
        df['cn_code'].str.startswith('25'),
        'sector'
    ] = 'Cement'

    df.loc[
        df['cn_code'].str.startswith(('28', '31')),
        'sector'
    ] = 'Fertilisers'

    df.loc[
        df['cn_code'].str.startswith('2804'),
        'sector'
    ] = 'Hydrogen'

    print(df.columns.tolist())

    rows.append(
    df[[
        'sector',
        'cn_code',
        'description',
        'total',
        'production_process_route'
    ]].assign(country=country)[[
        'country',
        'sector',
        'cn_code',
        'description',
        'total',
        'production_process_route']]
    )

result = pd.concat(rows, ignore_index=True)

result = result[result['sector'] != 'Other'].copy()

result.columns = [
    'country',
    'sector',
    'cn_code',
    'product_description',
    'default_total_emissions',
    'production_process_route'
]

result['unit'] = 'tCO2e/tonne'

result.to_csv('data/gcc_embedded_emissions_data.csv', index=False)

print(f"Created gcc_embedded_emissions_data.csv with {len(result)} rows")
print(result.head(20))