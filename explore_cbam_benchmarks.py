import pandas as pd
import re

# ============================================
# EU CBAM Benchmarks Extraction (Column B)
# ============================================

# Read the Benchmarks sheet
benchmark_file = "data/benchmarks.xlsx"
df = pd.read_excel(benchmark_file, sheet_name='Benchmarks', header=0)

print(f"Total rows in Excel: {len(df)}")

# Extract data
current_sector = None
current_cn_code = None
results = []

route_descriptions = {
    'A': 'A — Grey clinker/cement',
    'B': 'B — White clinker/cement',
    'C': 'C — Carbon steel BF/BOF',
    'D': 'D — Carbon steel DRI/EAF',
    'E': 'E — Carbon steel scrap/EAF',
    'F': 'F — Low alloy steel BF/BOF',
    'G': 'G — Low alloy steel DRI/EAF',
    'H': 'H — Low alloy steel scrap/EAF',
    'J': 'J — High alloy steel EAF',
    'K': 'K — Primary aluminium',
    'L': 'L — Secondary aluminium'
    }

for idx, row in df.iterrows():
    cn_code = row['CN code']
    description = row['CN Description']
    
    # Column B: Extract values (Column E) and indicator (Column F)
    col_b_benchmark = row['Column B\nBMg [tCO2e/t]']
    col_b_indicator = row['Column B\nProduction route indicator']
    
    # ========== STEP 1: Detect sector headers ==========
    if isinstance(cn_code, str) and not str(cn_code)[0].isdigit():
        current_sector = cn_code
        current_cn_code = None
        continue
    
    # ========== STEP 2: Update CN code ==========
    if pd.notna(cn_code) and isinstance(cn_code, (str, int)):
        cn_str = str(cn_code).strip()
        if cn_str and cn_str[0].isdigit():
            current_cn_code = cn_str

    
    # STEP 3: Validate row
    if pd.notna(col_b_benchmark) and current_sector and current_cn_code:

        # STEP 4: Extract indicators
        indicator_str = (
            str(col_b_indicator).strip()
            if pd.notna(col_b_indicator) else ""
        )

        # Extract year indicator (1) or (2)
        year_match = re.search(r'\(([12])\)', indicator_str)
        year_indicator = year_match.group(1) if year_match else None

        # Extract production route indicator A-L, excluding I
        route_match = re.search(r'\(([A-HJ-L])\)', indicator_str)
        route_indicator = route_match.group(1) if route_match else None

        # Create readable production process/route
        production_process_route = (
            route_descriptions[route_indicator]
            if route_indicator in route_descriptions
            else 'route_independent'
        )

        # STEP 5: Keep 2026–2027 values
        if year_indicator == '2':
            continue

        if year_indicator is None:
            year_indicator = '1'

        # STEP 6: Add to results
        results.append({
            'sector': current_sector,
            'cn_code': current_cn_code,
            'description': description if pd.notna(description) else '',
            'year_indicator': year_indicator,
            'production_process_route': production_process_route,
            'benchmark_value': float(col_b_benchmark),
            'production_route_original': (
                col_b_indicator if pd.notna(col_b_indicator) else ''
            ),
            'unit': 'tCO2e/tonne'
        })        
    

# ========== Create DataFrame ==========
final_df = pd.DataFrame(results)

print(f"\n✅ Total extracted: {len(final_df)}")
print(f"\nBreakdown by sector:")
print(final_df['sector'].value_counts())
print(f"\nBreakdown by year indicator:")
print(final_df['year_indicator'].value_counts())
print(f"\nBreakdown by production process/route:")
print(final_df['production_process_route'].value_counts())

# ========== Save CSV ==========
final_df.to_csv('data/cbam_benchmarks.csv', index=False)
print(f"\n✅ Saved to: cbam_benchmarks.csv")
print(f"\nSample rows:")
print(final_df.head(20))