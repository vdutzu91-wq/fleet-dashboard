import streamlit as st
import pandas as pd
import plotly.express as px
from io import BytesIO
from fpdf import FPDF
import datetime

st.set_page_config(page_title="Fleet Dashboard", layout="wide")

st.title("🚛 Fleet Dashboard")
st.markdown("Upload your Excel file and view real-time Profit/Loss reports with filters, charts, and exports.")

uploaded_file = st.file_uploader("📂 Upload Excel File", type=["xlsx"])

if uploaded_file is not None:
    # ---------------- LOAD SHEETS ----------------
    try:
        income_df = pd.read_excel(uploaded_file, sheet_name="Income")
    except Exception:
        st.error("❌ Could not find 'Income' sheet in the file.")
        st.stop()

    # Load all sheets
    xls = pd.ExcelFile(uploaded_file)
    expense_sheets = {name: pd.read_excel(uploaded_file, sheet_name=name) for name in xls.sheet_names if name != "Income"}

    # Parse dates
    if "Pickup" in income_df.columns:
        income_df["Pickup_Date"] = pd.to_datetime(income_df["Pickup"].astype(str).str.split(",").str[0], errors="coerce")
    else:
        income_df["Pickup_Date"] = pd.NaT

    # ---------------- FILTERS ----------------
    st.sidebar.header("🔎 Filters")

    # Driver filter
    drivers = income_df["Driver"].dropna().unique().tolist()
    selected_driver = st.sidebar.multiselect("Select Driver(s)", drivers, default=drivers)

    # Date filter
    min_date = income_df["Pickup_Date"].min()
    max_date = income_df["Pickup_Date"].max()
    date_range = st.sidebar.date_input("Date Range", [min_date, max_date])

    # Apply filters
    df_filtered = income_df[income_df["Driver"].isin(selected_driver)]
    if len(date_range) == 2:
        start, end = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
        df_filtered = df_filtered[(df_filtered["Pickup_Date"] >= start) & (df_filtered["Pickup_Date"] <= end)]

    st.subheader("📊 Income Data (Filtered Preview)")
    st.dataframe(df_filtered.head())

    # ---------------- CALCULATE SUMMARY ----------------
    st.subheader("📈 Truck Summary")

    summary = df_filtered.groupby(["Truck", "Driver"]).agg(
        Total_Loads=("Inv Amt", "count"),
        Total_Inv_Amt=("Inv Amt", "sum"),
        Total_Net_Pay=("Net pay", "sum")
    ).reset_index()

    # Expense categories
    expense_cols = ["Loan Exp", "Insurance", "IFTA", "Plates", "Prepass", 
                    "Office", "Repairs", "Fuel", "Tolls", "Factoring Fee"]
    for col in expense_cols:
        summary[col] = 0.0

    # Simplified expense loader
    for sheet, df in expense_sheets.items():
        truck_col = None
        for col in df.columns:
            if "truck" in str(col).lower() or "unit" in str(col).lower():
                truck_col = col
                break
        if truck_col:
            amt_col = [c for c in df.columns if "amount" in str(c).lower() or "cost" in str(c).lower()]
            if amt_col:
                amt_col = amt_col[0]
                expenses = df.groupby(truck_col)[amt_col].sum().to_dict()
                # Map
                if "loan" in sheet.lower():
                    colname = "Loan Exp"
                elif "insur" in sheet.lower():
                    colname = "Insurance"
                elif "eld" in sheet.lower():
                    colname = "IFTA"
                elif "reg" in sheet.lower():
                    colname = "Plates"
                elif "prepass" in sheet.lower():
                    colname = "Prepass"
                elif "office" in sheet.lower():
                    colname = "Office"
                elif "repair" in sheet.lower() or "maint" in sheet.lower():
                    colname = "Repairs"
                elif "fuel" in sheet.lower():
                    colname = "Fuel"
                elif "toll" in sheet.lower():
                    colname = "Tolls"
                elif "driver" in sheet.lower():
                    colname = "Factoring Fee"
                else:
                    colname = None

                if colname:
                    for i, row in summary.iterrows():
                        if row["Truck"] in expenses:
                            summary.loc[i, colname] += expenses[row["Truck"]]

    # Calculations
    summary["Total Expenses"] = summary[expense_cols].sum(axis=1)
    summary["Profit/Loss"] = summary["Total_Net_Pay"] - summary["Total Expenses"]
    summary["Profit per Load"] = summary["Profit/Loss"] / summary["Total_Loads"]

    st.dataframe(summary.style.format({
        "Total_Inv_Amt": "${:,.2f}",
        "Total_Net_Pay": "${:,.2f}",
        "Total Expenses": "${:,.2f}",
        "Profit/Loss": "${:,.2f}",
        "Profit per Load": "${:,.2f}"
    }))

    # ---------------- PLOTS ----------------
    st.subheader("📊 Visual Insights")

    # Profit per Truck (bar chart)
    fig_profit = px.bar(summary, x="Truck", y="Profit/Loss", color="Profit/Loss",
                        text="Profit/Loss", title="Profit/Loss per Truck")
    fig_profit.update_traces(texttemplate="$%{text:,.0f}", textposition="outside")
    st.plotly_chart(fig_profit, use_container_width=True)

    # Expense Breakdown (per truck)
    truck_choice = st.selectbox("🔎 Select a Truck for Expense Breakdown", summary["Truck"])
    truck_row = summary[summary["Truck"] == truck_choice].iloc[0]

    expense_data = {col: truck_row[col] for col in expense_cols}
    exp_df = pd.DataFrame(list(expense_data.items()), columns=["Category", "Amount"])
    exp_df = exp_df[exp_df["Amount"] > 0]

    fig_expense = px.pie(exp_df, names="Category", values="Amount", 
                         title=f"Expense Breakdown - Truck {truck_choice}")
    st.plotly_chart(fig_expense, use_container_width=True)

    # ---------------- EXPORTS ----------------
    st.subheader("📤 Export Reports")

    # Export to Excel
    def to_excel(df):
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Report")
        return output.getvalue()

    excel_data = to_excel(summary)
    st.download_button(label="⬇️ Download Excel Report", data=excel_data,
                       file_name="Fleet_Report.xlsx", mime="application/vnd.ms-excel")

    # Export to PDF
    def to_pdf(df):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 14)
        pdf.cell(200, 10, "Fleet Report", ln=True, align="C")
        pdf.set_font("Arial", "", 10)
        
        # Table header
        for col in df.columns:
            pdf.cell(25, 8, str(col), 1)
        pdf.ln()
        
        # Rows
        for _, row in df.iterrows():
            for col in df.columns:
                if isinstance(row[col], (int, float)):
                    txt = str(round(row[col], 2))
                else:
                    txt = str(row[col])
                pdf.cell(25, 8, txt, 1)
            pdf.ln()
        
        return pdf.output()

    pdf_data = bytes(to_pdf(summary))
    st.download_button(label="⬇️ Download PDF Report", data=pdf_data,
                       file_name="Fleet_Report.pdf", mime="application/pdf")