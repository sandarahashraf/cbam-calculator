"""
CBAM Cost Calculation Engine
=============================
Implements EU CBAM Regulation 2023/956 definitive regime calculations
Formula: CBAM Cost = (Embedded Emissions Intensity - CBAM Benchmark * CBAM Factor) * Quantity * EU ETS Price - Carbon Price Paid Abroad
 
Commission Implementing Regulation (EU) 2025/2620 specifies:
- CBAM Factor 2026: 0.975 (97.5% free allocation, 2.5% chargeable)
- Benchmark values: Column B from Regulation
- Year indicators: (1) for 2026-27, (2) for 2028-30; no indicator defaults to (1)
"""
 
import pandas as pd
from typing import Dict, List, Optional

 
# ============================================================
# CONFIGURATION
# ============================================================



# CBAM factor value for 2026 is 0.975 means 97.5% free allocation. 
CBAM_FACTOR = 0.975 


SECTOR_MARKUP = {
    "Fertilisers": {2026: 0.01, 2027: 0.01, 2028: 0.01},
    "default":     {2026: 0.10, 2027: 0.20, 2028: 0.30},
}

def get_marked_up_default(base_value, sector, year=2026):
    rates = SECTOR_MARKUP.get(sector, SECTOR_MARKUP["default"])
    return base_value * (1 + rates[year])


# CBAM certificate prices for each quarter of 2026 (PRICES ARE IN EUROS PER TONNE OF CO2e)
CBAM_CERTIFICATE_PRICES = {
    'Q1': 75.36,
    'Q2': 75.28,
    'Q3': 82.32,
    'Q4': None # TBD
    }


OTHER_COUNTRY = "Other Countries and Territories"      


# Data files
CBAM_BENCHMARK_FILE = "data/cbam_benchmarks.csv"
EMBEDDED_EMISSIONS_FILE = "data/gcc_embedded_emissions_data.csv"
 

 
# CBAM Sectors
CBAM_SECTORS = ['Cement', 'Hydrogen', 'Fertilisers', 'Iron & Steel', 'Aluminium']


PRODUCTION_ROUTE_NAMES = {
    'A': 'Grey clinker / cement',
    'B': 'White clinker / cement',
    'C': 'Carbon steel (BF/BOF)',
    'D': 'Carbon steel (DRI/EAF)',
    'E': 'Carbon steel (Scrap/EAF)',
    'F': 'Low alloy steel (BF/BOF)',
    'G': 'Low alloy steel (DRI/EAF)',
    'H': 'Low alloy steel (Scrap/EAF)',
    'J': 'High alloy steel (EAF)',
    'K': 'Primary aluminium',
    'L': 'Secondary aluminium',
    'standard': 'Standard route',
}
 
 
# ============================================================
# DATA LOADING
# ============================================================
 
class CBAMBenchmarkLoader:
    """Load and cache CBAM benchmark values from CSV"""
    
    def __init__(self, filepath: str = CBAM_BENCHMARK_FILE):
        self.filepath = filepath
        self.df = None
        self.load()
    
    def load(self):
        """Load CBAM benchmarks CSV"""
        try:
            df = pd.read_csv(self.filepath, dtype={"cn_code": str})
            df["product_type"] = (
                df["production_route_original"].astype(str)
                .str.extract(r"\(([A-HJ-L])\)")[0]
                .fillna("standard")
            )
            df["year_indicator"] = df["year_indicator"].fillna("1").astype(str)
            self.df = df
            print(f"✓ Loaded {len(self.df)} CBAM  benchmark rows from {self.filepath}")
        except FileNotFoundError:
            print(f"❌ Error: CBAM Benchmark file not found at {self.filepath}")
            self.df = pd.DataFrame()
            
    
    def get_benchmark(self, cn_code: str, product_type: str = 'standard',
                      year_indicator: str = '1') -> Optional[float]:
        if self.df.empty:
            return None

        codes = self.df['cn_code'].astype(str)
        year_ok = self.df['year_indicator'].astype(str) == str(year_indicator)
        type_ok = self.df['product_type'].astype(str) == str(product_type)

        # 1. Exact 8-digit match
        exact = self.df[(codes == str(cn_code)) & year_ok & type_ok]
        if not exact.empty:
            return float(exact.iloc[0]['benchmark_value'])

        # 2. Heading-level code (e.g. 7601): use the benchmarks under it
        under = self.df[codes.str.startswith(str(cn_code)) & year_ok & type_ok]
        if under.empty:
            return None

        values = under['benchmark_value'].astype(float)
        if values.nunique() > 1:
            print(f"⚠️ Benchmarks differ under CN {cn_code} ({product_type}): "
                  f"{values.min():.3f} to {values.max():.3f}. Using the highest.")
        return float(values.max())

    def get_benchmark_codes(self, cn_code: str, product_type: str = 'standard',
                            year_indicator: str = '1') -> List[str]:
        """8-digit benchmark codes that sit under a default (heading) code."""
        if self.df.empty:
            return []
        codes = self.df['cn_code'].astype(str)
        ok = (
            (self.df['year_indicator'].astype(str) == str(year_indicator)) &
            (self.df['product_type'].astype(str) == str(product_type))
        )
        return sorted(codes[codes.str.startswith(str(cn_code)) & ok].unique().tolist())

def get_benchmark_codes(cn_code: str, product_type: str = 'standard') -> List[str]:
        benchmarks, _ = _get_loaders()
        return benchmarks.get_benchmark_codes(cn_code, product_type)
 
class GCCDefaultEmbeddedEmissionsLoader:
    """Load and cache default emission values from CSV"""
    
    def __init__(self, filepath: str = EMBEDDED_EMISSIONS_FILE):
        self.filepath = filepath
        self.df = None
        self.load()
    
    def load(self):
        """Load  GCC default embedded emissions CSV"""
        try:
            df = pd.read_csv(self.filepath, dtype={"cn_code": str})
            df = df.rename(columns={
                "default_total_emissions": "default_emissions",
                "production_process_route": "production_route",
            })
            df["production_route"] = (
                df["production_route"].astype(str).str.strip("()")
                .replace({"nan": "standard", "": "standard"})
            )
            self.df = df
            print(f"✓ Loaded {len(self.df)} default embedded emission rows from {self.filepath}")
        except FileNotFoundError:
            print(f"❌ Error: Default embedded emissions file not found at {self.filepath}")
            self.df = pd.DataFrame()

    def get_default_emissions(self, country: str, cn_code: str,
                              production_route: str = 'standard') -> Optional[float]:
        if self.df.empty:
            return None
        match = self.df[
            (self.df['country'].astype(str).str.lower() == str(country).lower()) &
            (self.df['cn_code'].astype(str) == str(cn_code)) &
            (self.df['production_route'].astype(str) == str(production_route))
        ]
        if match.empty:
            return None
        return float(match.iloc[0]['default_emissions'])

    def get_default_info(self, country, cn_code, production_route='standard'):
        """Returns (value, source_country). Uses the 'Other' table if the country has no value."""
        value = self.get_default_emissions(country, cn_code, production_route)
        if value is not None:
            return value, country
        value = self.get_default_emissions(OTHER_COUNTRY, cn_code, production_route)
        if value is not None:
            return value, OTHER_COUNTRY
        return None, None
            
    
    def get_country_emissions(self, country: str) -> pd.DataFrame:
        """Get all emission values for a specific country"""
        if self.df.empty:
            return pd.DataFrame()
        
        return self.df[self.df['country'].astype(str).str.lower() == str(country).lower()]
    
    
    def get_available_countries(self) -> List[str]:
        """Get list of countries in dataset"""
        if self.df.empty:
            return []
        
        return self.df['country'].unique().tolist()
    
def get_default_info(country, cn_code, production_route='standard'):
    _, emissions = _get_loaders()
    return emissions.get_default_info(country, cn_code, production_route)    
  
 
# ============================================================
# CBAM CALCULATION FUNCTIONS
# ============================================================
 
def get_certificate_price(quarter: str) -> Optional[float]:
    """
    Get EU ETS certificate price for specified quarter 2026
    
    Args:
        quarter: 'Q1', 'Q2', 'Q3', or 'Q4'
    
    Returns:
        Price in €/tCO2e or None if TBD
    """
    quarter = quarter.upper()
    if quarter not in CBAM_CERTIFICATE_PRICES:
        print(f"❌ Invalid quarter: {quarter}. Use Q1, Q2, Q3, Q4")
        return None
    
    price = CBAM_CERTIFICATE_PRICES[quarter]
    if price is None:
        print(f"⚠️  Warning: Q4 2026 certificate price not yet available (TBD)")
    
    return price
 
 
def calculate_cbam_cost(
    embedded_emissions: float,
    cbam_benchmark: float,
    quantity: float,
    certificate_price: float,
    carbon_price_paid_abroad: float = 0,
    cbam_factor: float = CBAM_FACTOR
) -> Dict[str, float]:
    """
    Calculate CBAM cost following EU Regulation 2023/956
    
    Formula: CBAM Cost = (Embedded Emissions Intensity - CBAM Benchmark * CBAM Factor) * Quantity * Certificate Price - Carbon Price Paid Abroad
    
    Args:
        embedded_emissions: tCO2e/tonne (verified or default emissions intensity)
        cbam_benchmark: tCO2e/tonne (from Commission Implementing Regulation 2025/2620)
        quantity: tonnes of imported goods
        certificate_price: €/tCO2e (quarterly EU ETS price)
        carbon_price_paid_abroad: € (carbon tax/price already paid in exporting country)
        cbam_factor: Free allocation factor (default 0.975 for 2026)
    
    Returns:
        Dict with calculation breakdown:
        {
            'free_allocation': Free allocation benchmark (€/tonne),
            'chargeable_intensity': Chargeable emissions intensity (tCO2e/tonne),
            'total_chargeable_emissions': Total chargeable emissions (tCO2e),
            'cost_before_offset': CBAM cost before carbon price offset (€),
            'carbon_price_paid_abroad': Carbon price already paid (€),
            'cbam_cost': Final CBAM cost due (€),
            'cbam_cost_per_tonne': CBAM cost per tonne imported (€/tonne)
        }
    """
    
    if embedded_emissions < 0 or cbam_benchmark < 0 or quantity < 0 or certificate_price < 0:
        raise ValueError("All input values must be non-negative")
    
    if quantity == 0:
        return {
            'free_allocation': cbam_benchmark * cbam_factor,
            'chargeable_intensity': embedded_emissions - (cbam_benchmark * cbam_factor),
            'total_chargeable_emissions': 0,
            'cost_before_offset': 0,
            'carbon_price_paid_abroad': carbon_price_paid_abroad,
            'cbam_cost': 0,
            'cbam_cost_per_tonne': 0
        }
    
    # Step 1: Calculate free allocation based on CBAM benchmark and CBAM factor
    free_allocation_per_tonne = cbam_benchmark * cbam_factor
    
    # Step 2: Calculate chargeable emissions intensity
    chargeable_intensity = embedded_emissions - free_allocation_per_tonne
    
    # Step 3: Calculate total chargeable emissions (tonnes × intensity)
    total_chargeable_emissions = chargeable_intensity * quantity
    
    # Step 4: Calculate CBAM cost before carbon price offset
    cost_before_offset = total_chargeable_emissions * certificate_price
    
    # Step 5: Apply carbon price paid abroad offset
    cbam_cost = max(0, cost_before_offset - carbon_price_paid_abroad)
    
    # Cost per tonne of imported goods
    cbam_cost_per_tonne = cbam_cost / quantity if quantity > 0 else 0
    
    return {
        'free_allocation': free_allocation_per_tonne,
        'chargeable_intensity': chargeable_intensity,
        'total_chargeable_emissions': total_chargeable_emissions,
        'cost_before_offset': cost_before_offset,
        'carbon_price_paid_abroad': carbon_price_paid_abroad,
        'cbam_cost': cbam_cost,
        'cbam_cost_per_tonne': cbam_cost_per_tonne
    }
 
 
def calculate_quarter_comparison(
    embedded_emissions: float,
    cbam_benchmark: float,
    quantity: float,
    carbon_price_paid_abroad: float = 0
) -> Dict[str, Optional[Dict[str, float]]]:
    """Calculate CBAM cost for the same shipment in each 2026 quarter"""
    results = {}
    for quarter, price in CBAM_CERTIFICATE_PRICES.items():
        if price is None:
            results[quarter] = None   # Q4 not yet published
            continue
        calc = calculate_cbam_cost(
            embedded_emissions=embedded_emissions,
            cbam_benchmark=cbam_benchmark,
            quantity=quantity,
            certificate_price=price,
            carbon_price_paid_abroad=carbon_price_paid_abroad,
        )
        calc['certificate_price'] = price
        results[quarter] = calc
    return results


# ============================================================
# INITIALIZATION & TESTING
# ============================================================
 
def test_calculation():
    """Test CBAM calculation with example values"""
    
    print("\n" + "="*70)
    print("EU CBAM COST CALCULATION - TEST CASE")
    print("="*70)
    
    # Example: Saudi Arabia steel export to EU
    # Steel CN code: 7302919900 (Other than in coils, of iron or steel, not alloyed)
    # Production route: DRI/EAF (Product type D)
    
    print("\n📋 SCENARIO: Saudi Arabia Steel Export")
    print("-" * 70)
    
    embedded_emissions = 2.1  # tCO2e/tonne (DRI/EAF route - low emissions)
    cbam_benchmark = 2.95    # tCO2e/tonne (from Regulation 2025/2620 Column B)
    quantity = 1000           # tonnes
    certificate_price = 75.36 # €/tCO2e (Q1 2026 price)
    carbon_price_paid = 0     # € (no carbon tax paid in Saudi Arabia)
    
    print(f"Embedded Emissions Intensity: {embedded_emissions:.2f} tCO2e/tonne")
    print(f"CBAM Benchmark (Column B): {cbam_benchmark:.2f} tCO2e/tonne")
    print(f"Quantity: {quantity:.0f} tonnes")
    print(f"EU ETS Certificate Price (Q1 2026): €{certificate_price:.2f}/tCO2e")
    print(f"Carbon Price Paid Abroad: €{carbon_price_paid:.2f}")
    print(f"CBAM Factor 2026: {CBAM_FACTOR} (97.5% free allocation)")
    
    # Calculate
    result = calculate_cbam_cost(
        embedded_emissions=embedded_emissions,
        cbam_benchmark=cbam_benchmark,
        quantity=quantity,
        certificate_price=certificate_price,
        carbon_price_paid_abroad=carbon_price_paid,
        cbam_factor=CBAM_FACTOR
    )
    
    print("\n📊 CALCULATION BREAKDOWN:")
    print("-" * 70)
    print(f"Step 1 - Free Allocation Benchmark: {result['free_allocation']:.4f} tCO2e/tonne")
    print(f"  = {cbam_benchmark:.2f} × {CBAM_FACTOR} = {result['free_allocation']:.4f}")
    print(f"\nStep 2 - Chargeable Emissions Intensity: {result['chargeable_intensity']:.4f} tCO2e/tonne")
    print(f"  = {embedded_emissions:.2f} - {result['free_allocation']:.4f} = {result['chargeable_intensity']:.4f}")
    print(f"\nStep 3 - Total Chargeable Emissions: {result['total_chargeable_emissions']:.2f} tCO2e")
    print(f"  = {result['chargeable_intensity']:.4f} × {quantity:.0f} = {result['total_chargeable_emissions']:.2f}")
    print(f"\nStep 4 - CBAM Cost (before offset): €{result['cost_before_offset']:.2f}")
    print(f"  = {result['total_chargeable_emissions']:.2f} × €{certificate_price:.2f} = €{result['cost_before_offset']:.2f}")
    print(f"\nStep 5 - Apply Carbon Price Offset: €{carbon_price_paid:.2f}")
    print(f"\nStep 6 - Final CBAM Cost: €{result['cbam_cost']:.2f}")
    print(f"  = €{result['cost_before_offset']:.2f} - €{carbon_price_paid:.2f} = €{result['cbam_cost']:.2f}")
    print(f"\nCBAM Cost per Tonne: €{result['cbam_cost_per_tonne']:.2f}/tonne")
    
    # Scenario analysis
    print("\n" + "="*70)
    print("📈 SCENARIO ANALYSIS: Certificate Price Variations")
    print("="*70)
    
    scenarios = calculate_quarter_comparison(
        embedded_emissions=embedded_emissions,
        cbam_benchmark=cbam_benchmark,
        quantity=quantity,
        carbon_price_paid_abroad=carbon_price_paid
    )
    
    for scenario_name, calc in scenarios.items():
        price_used = calc['cost_before_offset'] / calc['total_chargeable_emissions'] if calc['total_chargeable_emissions'] > 0 else 0
        print(f"\n{scenario_name.upper()}:")
        print(f"  Certificate Price: €{price_used:.2f}/tCO2e")
        print(f"  CBAM Cost: €{calc['cbam_cost']:.2f}")
        print(f"  Cost per Tonne: €{calc['cbam_cost_per_tonne']:.2f}/tonne")
    
    print("\n" + "="*70)
 
 
if __name__ == "__main__":
    # Initialize loaders
    print("🔧 Initializing CBAM Calculation Engine...")
    benchmarks = CBAMBenchmarkLoader()
    emissions = GCCDefaultEmbeddedEmissionsLoader()
    
    # Run test
    test_calculation()
    
    print("\n✅ CBAM Calculation Engine Ready")
    print(f"   - Benchmarks loaded: {len(benchmarks.df)} rows")
    print(f"   - Default emissions loaded: {len(emissions.df)} rows")
 
 
# ============================================================
# STREAMLIT APP INTERFACE FUNCTIONS
# ============================================================
 
# Global instances for Streamlit app
_benchmark_loader = None
_emissions_loader = None
 
def _get_loaders():
    """Initialize and cache data loaders"""
    global _benchmark_loader, _emissions_loader
    if _benchmark_loader is None:
        _benchmark_loader = CBAMBenchmarkLoader()
    if _emissions_loader is None:
        _emissions_loader = GCCDefaultEmbeddedEmissionsLoader()
    return _benchmark_loader, _emissions_loader
 
 
def get_exportable_countries() -> List[str]:
    """Countries available for selection (excludes the fallback table)"""
    _, emissions = _get_loaders()
    return sorted(c for c in emissions.get_available_countries() if c != OTHER_COUNTRY)
 
 
def get_exportable_products(country):
    _, emissions = _get_loaders()
    df = emissions.df
    own = df[df["country"] == country]
    other = df[df["country"] == OTHER_COUNTRY]
    if other.empty:
        return own.reset_index(drop=True)
    keys = set(zip(own["cn_code"], own["production_route"]))
    mask = [(c, r) not in keys for c, r in zip(other["cn_code"], other["production_route"])]
    return pd.concat([own, other[mask]], ignore_index=True)
 
 
def get_default_emissions(country: str, cn_code: str, production_route: str = 'standard') -> Optional[float]:
    _, emissions = _get_loaders()
    return emissions.get_default_emissions(country, cn_code, production_route)
 
 
def get_benchmark(cn_code: str, product_type: str = 'standard') -> Optional[float]:
    benchmarks, _ = _get_loaders()
    return benchmarks.get_benchmark(cn_code, product_type)
 
 
def calculate_cbam_liability(
    actual_emissions: float,
    benchmark_value: float,
    quantity: float,
    certificate_price: float,
    carbon_price_paid: float = 0
) -> Dict[str, float]:
    """
    Calculate CBAM liability for Streamlit app
    Returns dict with keys compatible with app_cbam.py
    """
    
    result = calculate_cbam_cost(
        embedded_emissions=actual_emissions,
        cbam_benchmark=benchmark_value,
        quantity=quantity,
        certificate_price=certificate_price,
        carbon_price_paid_abroad=carbon_price_paid,
        cbam_factor=CBAM_FACTOR
    )
    
    # Transform to app-compatible format
    return {
        'actual_emissions': actual_emissions,
        'benchmark_value': benchmark_value,
        'free_allocation': result['free_allocation'],
        'chargeable_emissions': result['chargeable_intensity'],
        'quantity': quantity,
        'cbam_certificates': max(0, result['total_chargeable_emissions']),
        'certificate_price': certificate_price,
        'cbam_cost': max(0, result['cost_before_offset']),
        'carbon_price_paid': carbon_price_paid,
        'net_liability': result['cbam_cost'],
        'cost_per_tonne': result['cbam_cost_per_tonne']
    }