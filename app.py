import streamlit as st
import pandas as pd

from calculation_cbam import (
    calculate_quarter_comparison,
    get_exportable_countries,
    get_exportable_products,
    get_default_info,
    get_benchmark,
    get_certificate_price,
    get_marked_up_default,
    calculate_cbam_liability,
    PRODUCTION_ROUTE_NAMES,
)
 
st.set_page_config(
    page_title="EU CBAM Calculator",
    page_icon="🍃",
    layout="wide"
)
 
st.title("🍃📦 EU CBAM Carbon & Financial Impact Assessment Tool")
st.markdown("""
Estimate the Carbon Border Adjustment Mechanism (CBAM) financial impact
for your GCC-manufactured goods exported to the EU.
""")
 
# Sidebar inputs
st.sidebar.header("📋 Product Information")
 
# Step 1: Select Country
countries = get_exportable_countries()
selected_country = st.sidebar.selectbox(
    "🏭 Country of Origin",
    countries
)
 
# Step 2: Select Product
products = get_exportable_products(selected_country)
product_options = products.apply(
    lambda x: f"{x['sector']} - {x['product_description'][:50]} (CN {x['cn_code']})",
    axis=1
).tolist()
 
selected_product_idx = st.sidebar.selectbox(
    "📦 Product",
    range(len(product_options)),
    format_func=lambda x: product_options[x]
)
 
selected_product = products.iloc[selected_product_idx]
route = str(selected_product['production_route'])
route_name = PRODUCTION_ROUTE_NAMES.get(route, route)
cn_code = str(selected_product['cn_code'])
sector = selected_product['sector']
 
# Step 3: Emissions Data
st.sidebar.markdown("---")
st.sidebar.header("💨 Emissions Data")
 
emissions_source = st.sidebar.radio(
    "Emissions Type",
    ["Use Default Value"]
)
st.sidebar.caption("Actual verified emissions are not yet supported in this tool.")

default_emissions, _ = get_default_info(selected_country, cn_code, route)
if default_emissions is not None:
    emissions = get_marked_up_default(default_emissions, sector, 2026)
    markup_pct = (emissions / default_emissions - 1) * 100
    st.sidebar.info(
        f"**Default (base):** {default_emissions:.3f} tCO2e/tonne\n\n"
        f"**Marked-up default (+{markup_pct:.0f}%):** {emissions:.3f} tCO2e/tonne"
    )
else:
    emissions = None
    st.sidebar.warning("No default value available for this product")
 
# Step 4: Production Route & Benchmark
st.sidebar.markdown("---")
st.sidebar.header("📊 Benchmark Selection")
 
benchmark = get_benchmark(cn_code, route)

if benchmark is not None:
    st.sidebar.info(
        f"**Production route:** {route_name}\n\n"
        f"**Benchmark:** {benchmark:.3f} tCO2e/tonne"
    )
else:
    st.sidebar.warning("No benchmark for this product and route")
    
# Step 5: Trade Data
st.sidebar.markdown("---")
st.sidebar.header("📦 Trade & Pricing")
 
quantity = st.sidebar.number_input(
    "Quantity (tonnes)",
    min_value=0.0,
    value=100.0,
    step=10.0
)
 
quarter = st.sidebar.selectbox(
    "Import Quarter (2026)",
    ["Q1", "Q2", "Q3", "Q4"],
    index=0
)
 
certificate_price = get_certificate_price(quarter)
if certificate_price is None:
    st.sidebar.warning(f"Price for {quarter} not yet published. Enter manually:")
    certificate_price = st.sidebar.number_input(
        "CBAM Certificate Price (€/tCO2e)",
        min_value=0.0,
        value=75.0,
        step=0.01
    )
else:
    st.sidebar.info(f"**Certificate Price {quarter}:** €{certificate_price:.2f}/tCO2e")
 
carbon_price_paid = st.sidebar.number_input(
    "Carbon Price Already Paid in Origin (€)",
    min_value=0.0,
    value=0.0,
    step=100.0
)
 
# Calculate button
st.sidebar.markdown("---")
calculate_btn = st.sidebar.button(
    "🔢 Calculate CBAM Impact",
    type="primary",
    use_container_width=True
)
 
# Results section
if calculate_btn and benchmark is None:
    st.error("No benchmark value for this product and route, so CBAM cannot be calculated. Choose a different product or check the benchmark data.")
elif calculate_btn:
    try:
        result = calculate_cbam_liability(
            actual_emissions=emissions,
            benchmark_value=benchmark,
            quantity=quantity,
            certificate_price=certificate_price,
            carbon_price_paid=carbon_price_paid
        )
 
        st.markdown("---")
        st.subheader("📊 CBAM Financial Impact Assessment")
 
        # Main metrics
        col1, col2, col3, col4 = st.columns(4)
 
        with col1:
            st.metric(
                label="CBAM Certificates Needed",
                value=f"{result['cbam_certificates']:,.0f}",
                help="tCO2e of CBAM certificates required"
            )
 
        with col2:
            st.metric(
                label="CBAM Cost",
                value=f"€{result['cbam_cost']:,.0f}",
                help="Total CBAM cost before carbon credits"
            )
 
        with col3:
            st.metric(
                label="Carbon Price Paid",
                value=f"€{result['carbon_price_paid']:,.0f}",
                help="Carbon tax already paid in origin country"
            )
 
        with col4:
            st.metric(
                label="Net CBAM Liability",
                value=f"€{result['net_liability']:,.0f}",
                delta=f"€{result['cost_per_tonne']:.2f}/tonne",
                help="Final amount to pay for CBAM"
            )
 
        # Detailed breakdown
        st.markdown("---")
        st.subheader("📈 Detailed Calculation Breakdown")
 
        col_left, col_right = st.columns(2)
 
        with col_left:
            st.markdown("**Emissions Analysis**")
            breakdown_df = pd.DataFrame({
                'Component': [
                    'Actual Emissions',
                    'Benchmark Value',
                    'Free Allocation (97.5% of Benchmark)',
                    'Chargeable Emissions'
                ],
                'Value (tCO2e/tonne)': [
                    result['actual_emissions'],
                    result['benchmark_value'],
                    result['free_allocation'],
                    result['chargeable_emissions']
                ]
            })
            st.dataframe(breakdown_df, hide_index=True, use_container_width=True)
 
        with col_right:
            st.markdown("**Financial Calculation**")
            financial_df = pd.DataFrame({
                'Item': [
                    'Quantity',
                    'Chargeable Emissions',
                    'CBAM Certificates',
                    'Certificate Price',
                    'CBAM Cost',
                    'Carbon Price Paid',
                    'Net Liability'
                ],
                'Value': [
                    f"{result['quantity']:.0f} tonnes",
                    f"{result['chargeable_emissions']:.3f} tCO2e/t",
                    f"{result['cbam_certificates']:,.0f} tCO2e",
                    f"€{result['certificate_price']:.2f}/tCO2e",
                    f"€{result['cbam_cost']:,.2f}",
                    f"€{result['carbon_price_paid']:,.2f}",
                    f"€{result['net_liability']:,.2f}"
                ]
            })
            st.dataframe(financial_df, hide_index=True, use_container_width=True)
 
        # Product & Regulatory Info
        st.markdown("---")
        st.subheader("ℹ️ Product & Regulatory Information")
 
        info_col1, info_col2, info_col3 = st.columns(3)
 
        with info_col1:
            st.markdown(f"**Country:** {selected_country}")
            st.markdown(f"**Sector:** {sector}")
 
        with info_col2:
            st.markdown(f"**CN Code:** {cn_code}")
            st.markdown(f"**Production Route:** {route_name}")
 
        with info_col3:
            st.markdown(f"**Import Quarter:** {quarter} 2026")
            st.markdown(f"**Regulation:** EU 2023/956")
 
        # Regulatory notes
        st.info(
            """
            ℹ️ **CBAM Overview:**
            - **Definitive regime:** Valid from 1 January 2026
            - **Free allocation:** 97.5% of benchmark emissions (2.5% chargeable)
            - **Benchmarks:** Standard production route per product from EU Commission
            - **Certificate prices:** Quarterly values based on EU ETS auction clearing prices
            - **Carbon credit:** Deduction allowed for carbon tax already paid in origin country
 
            📋 **Emissions options:**
            - Use default value from EU Commission (if available)
            - Report actual verified emissions (requires third-party verification)
 
            🔗 **References:**
            - EU Regulation 2023/956
            - Commission Implementing Regulation (EU) 2025/2620
            - Commission Implementing Regulation (EU) 2025/2621
            """
        )
 
        st.markdown("---")
        st.subheader("📊 Cost by Import Quarter")
        st.markdown("**Same shipment, different quarterly certificate prices**")

        quarter_results = calculate_quarter_comparison(
            embedded_emissions=emissions,
            cbam_benchmark=benchmark,
            quantity=quantity,
            carbon_price_paid_abroad=carbon_price_paid,
        )

        quarter_rows = []
        for q, calc in quarter_results.items():
            if calc is None:
                quarter_rows.append({
                    'Quarter': q,
                    'CBAM Certificate Price': 'TBD',
                    'CBAM Cost': 'Not yet published',
                    'Cost/Tonne': '-',
                })
            else:
                quarter_rows.append({
                    'Quarter': q,
                    'CBAM Certificate Price': f"€{calc['certificate_price']:.2f}",
                    'CBAM Cost': f"€{calc['cbam_cost']:,.0f}",
                    'Cost/Tonne': f"€{calc['cbam_cost_per_tonne']:.2f}/t",
                })

        st.dataframe(pd.DataFrame(quarter_rows), hide_index=True, use_container_width=True)
        
    except Exception as e:
        st.error(f"❌ Calculation error: {str(e)}")
          
else:
    st.info("👈 Enter product details and click **Calculate CBAM Impact** to see results")

st.markdown("---")
st.caption(
    "**Disclaimer:** This tool gives an estimate of EU CBAM costs for goods exported from "
    "GCC countries (Bahrain, Kuwait, Oman, Qatar, Saudi Arabia and the UAE), based on "
    "Regulation (EU) 2023/956 and Implementing Regulations (EU) 2025/2620 and 2025/2621. "
    "Calculations use EU default values, including the mark-up for the selected year, "
    "and the CBAM benchmark (Column B) for the product and production route. "
    "Actual verified emissions are not supported in this version. "
    "Results apply to 2026 only. The CBAM factor, cross-sectoral correction factor, "
    "certificate prices, benchmarks and default values are provisional or may change, "
    "and the tool is updated when official values change. "
    "The tool is for guidance only and is not legal or financial advice. "
    "Your final CBAM declaration may differ."
)       
 