import streamlit as st
import pandas as pd
import pulp
import networkx as nx
import matplotlib.pyplot as plt
import altair as alt

TITLE = "Transportation Solver"

st.set_page_config(
    page_title=TITLE,
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': 'https://www.extremelycoolapp.com/help',
        'Report a bug': "https://www.extremelycoolapp.com/bug",
        'About': "# This is a header. This is an *extremely* cool app!"
    }
)

st.title(TITLE)

st.markdown("""
This system creates the most cost-effective transportation plan using the data in the Excel file you upload.
""")

st.divider()



with st.expander(":yellow[How to prepare an excel file template?]"):
    st.markdown("For the system to function correctly, your Excel file must contain **3 sheets** :green[('Routes', 'Capacities', 'Demands')]. You can prepare your template by following the steps below.")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.info("Routes Page")
        st.markdown("Write here the point where the materials will be sourced from, the point where they will be delivered to, and the cost.")
        st.markdown("""
        * **Source:** Origin Name
        * **Target:** Destination Name
        * **Cost:** Unit transportation cost (per item/truck).
        * **Route_Capacity:** *:yellow[(Optional)]* Maximum flow limit for this specific path. :red[Leave blank if unlimited.]
        """)

        st.image("images/routes.png", caption="The routes page should look like this (data is for example purposes)")
    
    with col2:
        st.warning("Capacities Page")
        st.markdown("List only the **producers** or initial supply points here.")
        st.markdown("""
        * **Node:** Location Name (Must match exactly with 'Source' in Routes).
        * **Capacity:** Total production or supply limit.
        * **Note:** :red[Do not list intermediate depots here; the system identifies them automatically.]*
        """)
        
        st.image("images/capacity.png", caption="The capacities page should look like this")

    
    with col3:
        st.success("Demands Page")
        st.markdown("List only the **final destinations** (Customers/Branches) here.")
        st.markdown("""
        * **Node:** Location Name (Must match exactly with 'Target' in Routes).
        * **Demand:** Required quantity of goods.
        * **Note:** :red[Do not list intermediate depots here; they have no intrinsic demand.]*
        """)

        st.image("images/demand.png", caption="The demands page should look like this")




# --- File Upload

uploaded_file = st.file_uploader("Please upload your Excel file.")

if uploaded_file is not None:

    try:
        xls = pd.read_excel(uploaded_file, sheet_name=None)

        required_pages = ["Routes", "Capacities", "Demands"]
        missing_pages = [p for p in required_pages if p not in xls.keys()]

        if missing_pages:
            st.warning(f"Error! Missing sheets in Excel {','.join(missing_pages)}")
        
        else:
            df_routes = xls["Routes"]

            #--eğer hat kısıtı varsa
            if 'Route_Capacity' in df_routes.columns:
                df_routes['Route_Capacity'] = df_routes['Route_Capacity'].fillna(999999999)
            #-----------------------

            df_capacities = xls["Capacities"]
            df_demands = xls["Demands"]


            #-sütun yazı boşluk kontrolü
            df_routes.columns = df_routes.columns.str.strip()
            df_capacities.columns = df_capacities.columns.str.strip()
            df_demands.columns = df_demands.columns.str.strip()
            #-hücre yazıları boşluk kontrol
            df_routes['Source'] = df_routes['Source'].astype(str).str.strip()
            df_routes['Target'] = df_routes['Target'].astype(str).str.strip()
            df_capacities['Node'] = df_capacities['Node'].astype(str).str.strip()
            df_demands['Node'] = df_demands['Node'].astype(str).str.strip()


            tab1, tab2, tab3 = st.tabs(["Routes", "Capacities", "Demands"])

            with tab1:
                st.dataframe(df_routes, use_container_width=True)
                st.info(f"a total of {len(df_routes)} routes have been defined")

            with tab2:
                col1, col2 = st.columns([1,1])
                with col1:
                    st.dataframe(df_capacities, use_container_width=True)
                with col2:
                    chart_cap = alt.Chart(df_capacities).mark_bar().encode(
                        x=alt.X('Node', sort='-y', title='Factory/Source'),
                        y=alt.Y('Capacity', title='Capacity'),
                        color=alt.Color('Node', legend=None), 
                        tooltip=['Node', 'Capacity'],
                    ).properties(title="Capacity distribution")
                    
                    st.altair_chart(chart_cap, use_container_width=True)

            with tab3:
                col1, col2 = st.columns([1,1])
                with col1:
                    st.dataframe(df_demands, use_container_width=True)
                with col2:
                    chart_dem = alt.Chart(df_demands).mark_bar().encode(
                        x=alt.X('Node', sort='-y', title='Branch/Customer'),
                        y=alt.Y('Demand', title='Demand'),
                        color=alt.Color('Node', legend=None),
                        tooltip=['Node', 'Demand']
                    ).properties(title="Demand Distribution")
                    
                    st.altair_chart(chart_dem, use_container_width=True)


            st.divider()


    except Exception as e:
        st.error(f"An error occurred while reading the file. {e}")






if st.button("Solve", type="primary"):
    with st.spinner("Optimazing transportation network...."):
        try:
            prob = pulp.LpProblem("Transportation_Problem", pulp.LpMinimize)

            route_caps = {}
            if 'Route_Capacity' in df_routes.columns:
                route_caps = {(row.Source, row.Target): row.Route_Capacity for index, row in df_routes.iterrows()}

            routes = [(row.Source, row.Target) for index, row in df_routes.iterrows()]

            #--rotaların maliyetler ile eşleştirilmesi
            costs = {(row.Source, row.Target): row.Cost for index, row in df_routes.iterrows()}

            flow = pulp.LpVariable.dicts("Route", routes, lowBound=0, cat="Continuous")

            #--amaç fonksiyonu
            prob += pulp.lpSum(flow[r] * costs[r] for r in routes), "Total_Transport_Cost"

            #--kısıtlar
            #-kapasite kısıtları
            for index, row in df_capacities.iterrows():
                node = row.Node
                capacity = row.Capacity
                prob += pulp.lpSum([flow[r] for r in routes if r[0] == node]) <= capacity, f"Cap_{node}"

            #-talep kısıtları
            for index, row in df_demands.iterrows():
                node = row.Node
                demand = row.Demand
                prob += pulp.lpSum([flow[r] for r in routes if r[1] == node]) >= demand, f"Dem_{node}"


            #-ara depo denge kısıtları
            all_nodes = set([r[0] for r in routes] + [r[1] for r in routes])
            supply_nodes = set(df_capacities['Node'])
            demand_nodes = set(df_demands['Node'])
            
            #-kesişim kümesi
            transshipment_nodes = all_nodes - supply_nodes - demand_nodes

            for node in transshipment_nodes:
                #-depolara girenler
                inflow = pulp.lpSum([flow[r] for r in routes if r[1] == node])
                
                #-depolardan çıkanlar
                outflow = pulp.lpSum([flow[r] for r in routes if r[0] == node])
                
                #-arz-talep eşitliği kısıtı
                prob += (inflow == outflow, f"Balance_{node}")


            #-rota kapasiteleri kısıtı
            for r in routes:
                if r in route_caps:
                    limit = route_caps[r]
                    prob += flow[r] <= limit, f"RouteCap_{r[0]}_{r[1]}"


            prob.solve()



            st.success(f"Optimization complate! Status: {pulp.LpStatus[prob.status]}")


            if pulp.LpStatus[prob.status] == "Optimal":
                st.subheader("Total Minimum Cost")
                # st.metric(label="Total Minimum Cost", value=f"${pulp.value(prob.objective):,.2f}")
                st.markdown(f"## ${pulp.value(prob.objective):,.2f}")



                st.divider()

                total_cost = pulp.value(prob.objective)
                total_flow = sum([flow[r].varValue for r in routes])
                active_routes = sum([1 for r in routes if flow[r].varValue > 0])
                avg_cost = total_cost / total_flow if total_flow > 0 else 0

                st.subheader("Operation Summary")
                kpi1, kpi2, kpi3, kpi4 = st.columns(4)
                
                kpi1.metric("Total Cost", f"${total_cost:,.2f}", delta_color="inverse", border=True)
                kpi2.metric("Total Transported Cargo (pcs)", f"{int(total_flow):,}", border=True)
                kpi3.metric("AVG Unit Cost", f"${avg_cost:.2f}", border=True)
                kpi4.metric("Active Route", f"{active_routes} / {len(routes)}", border=True)

                st.divider()

                results = []

                for r in routes:
                    var_value = flow[r].varValue
                    if var_value > 0:
                        results.append({
                            "Source":r[0],
                            "Target":r[1],
                            "Quantity":var_value,
                            "Unit Cost":costs[r],
                            "Total Cost": var_value * costs[r]
                        })


                df_results = pd.DataFrame(results)
                st.subheader("Optimized Shipment Plan")
                st.dataframe(df_results, use_container_width=True)
            
                st.divider()


                #-sonuç tablo verileri
                col1, col2 = st.columns(2)
                    
                with col1:
                    st.subheader("Number Of Outputs Based On Sender")
                    # Kaynağa göre grupla ve topla
                    source_summary = df_results.groupby("Source")["Quantity"].sum().reset_index()
                    
                    # Altair ile Renkli Grafik
                    chart_source = alt.Chart(source_summary).mark_bar().encode(
                        x=alt.X('Source', title='Source Node', sort='-y'),
                        y=alt.Y('Quantity', title='Toplam Miktar'),
                        color=alt.Color('Source', legend=None),
                        tooltip=['Source', 'Quantity']
                    ).properties(height=300)
                    
                    st.altair_chart(chart_source, use_container_width=True)
                
                with col2:
                        st.subheader("Total Demand by Buyer")
                        # Hedefe göre grupla ve topla
                        target_summary = df_results.groupby("Target")["Quantity"].sum().reset_index()
                        
                        # Altair ile Renkli Grafik
                        chart_target = alt.Chart(target_summary).mark_bar().encode(
                            x=alt.X('Target', title='Hedef Noktası', sort='-y'),
                            y=alt.Y('Quantity', title='Toplam Miktar'),
                            color=alt.Color('Target', legend=None), # <-- İŞTE SİHİR BURADA: Her hedefe farklı renk
                            tooltip=['Target', 'Quantity']
                        ).properties(height=300)
                        
                        st.altair_chart(chart_target, use_container_width=True)




                ##--csv dışa aktar
                csv = df_results.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="Download Plan as CSV",
                    data=csv,
                    file_name="optimal_plan.csv",
                    mime="text/csv",
                )



                st.divider()


                ##---haritalandırma
                st.subheader("Network Visualization")
                st.caption("The labels on the routes state that: [Quantity, Total Cost]", text_alignment="center")
                st.container()
                G = nx.DiGraph()
                
                for r in routes:
                    var_value = flow[r].varValue
                    if var_value > 0:
                        total_line_cost = var_value * costs[r]
                        label_text = f"[{int(var_value)}, ${int(total_line_cost):,}]"
                        G.add_edge(r[0], r[1], weight=var_value, label=label_text)


                suppliers = list(df_capacities['Node'].unique())  #-fabrikalar
                customers = list(df_demands['Node'].unique())     #-şubeler
                
                all_nodes_in_flow = set(G.nodes())
                transshipment = list(all_nodes_in_flow - set(suppliers) - set(customers))


                pos = {}
                
                for i, node in enumerate(suppliers):
                    if node in G.nodes():
                        pos[node] = (0, -i)

                middle_x = 1 if transshipment else 1 
                for i, node in enumerate(transshipment):
                    y_pos = -i * (len(suppliers) / max(len(transshipment), 1))
                    pos[node] = (middle_x, y_pos)

                #-katman kontrol
                right_x = 2 if transshipment else 1

                for i, node in enumerate(customers):
                    if node in G.nodes():
                        y_pos = -i * (len(suppliers) / max(len(customers), 1))
                        pos[node] = (right_x, y_pos)


                col1, col2, col3 = st.columns([1, 3, 1])

                with col2:
                    fig, ax = plt.subplots(figsize=(10, 5))

                    #-arzlar
                    nx.draw_networkx_nodes(G, pos, nodelist=[n for n in suppliers if n in G.nodes()], node_color='skyblue', node_size=800, node_shape='s', ax=ax, label="Factories")
                    
                    #-depolar
                    if transshipment:
                        nx.draw_networkx_nodes(G, pos, nodelist=transshipment, node_color='orange', node_size=800, node_shape='h', ax=ax, label="Depots")

                    #-talep edenler
                    nx.draw_networkx_nodes(G, pos, nodelist=[n for n in customers if n in G.nodes()], node_color='lightgreen', node_size=800, node_shape='o', ax=ax, label="Branches")

                    #-etiketler
                    nx.draw_networkx_labels(G, pos, font_size=9, font_weight='bold', ax=ax)

                    edges = G.edges(data=True)
                    weights = [data['weight'] * 0.008 for u, v, data in edges]
                    
                    nx.draw_networkx_edges(G, pos, width=weights, arrowstyle='->', arrowsize=20, edge_color='gray', connectionstyle="arc3", ax=ax)

                    edge_labels = nx.get_edge_attributes(G, 'label')
                    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, label_pos=0.6, font_color='red', font_size=8, ax=ax)

                    ax.legend(loc='upper center', bbox_to_anchor=(0.5, 1.1), ncol=3, frameon=False)
                    
                    plt.margins(x=0.2)
                    plt.axis('off')
                    st.pyplot(fig)

            
            else:
                st.error("Problem could be solved. Please chechk capacities and demands (Infeasible).")



        except Exception as e:
                    st.error(f"An error occurred during optimization: {e}")




st.divider()
st.caption("Made By Can Emirhan ALKAN", text_alignment="center")






