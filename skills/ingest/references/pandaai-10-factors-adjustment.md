---
source: https://www.pandaai.online/knowledge-base/?pageUrl=/coreFeatrue&id=%E4%BA%94%E6%95%B0%E6%8D%AEapi
title: PandaAI Data API - Backtest Factors and Adjustment Factors
extracted: 2026-05-06
source_lines: 3622-4220
---

**5. 获取回测因子**

**5.1. 方法名：get_factor**

**5.2. 入参**

| 字段 | 类型 | 描述 | 是否必填 |
|:---|:---|:---|:---|
| start_date | str | 开始日期,eg:"20250702" | 必填 |
| end_date | str | 结束日期,eg:"20250702" | 必填 |
| symbol | Optional\[Union\[str, List\[str\]\]\] | 股票代码 | 非必填 |
| factors | Union\[str, List\[str\]\] | 因子列表 | 必填 |
| type | Optional\[str\] | 产品类型，支持"stock" ,"future"，默认为"stock" | 非必填 |
| index_component | Optional\[str\] | 指数成分股过滤条件,可选项有沪深300:"100",中证500:"010",中证1000:"001",非上述指数成分股:"000" | 非必填 |

**5.3. 响应参数**

基础因子类:

股票:

| 字段            | 类型   | 描述     |
|:----------------|:-------|:---------|
| date            | str    | 日期     |
| symbol          | str    | 股票代码 |
| name            | str    | 股票名称 |
| open            | double | 开盘价   |
| close           | double | 收盘价   |
| high            | double | 最高价   |
| low             | double | 最低价   |
| volume          | double | 成交量   |
| amount          | double | 成交额   |
| index_component | str    | 股票池   |
| market_cap      | double | 市值     |
| turnover        | double | 换手率   |

期货:

| 字段              | 类型   | 描述         |
|:------------------|:-------|:-------------|
| date              | str    | 日期         |
| symbol            | str    | 期货代码     |
| dominant_id       | str    | 主力合约代码 |
| exchange          | str    | 交易所       |
| trading_code      | str    | 交易代码     |
| underlying_symbol | str    | 期货品种     |
| open              | double | 当日开盘价   |
| close             | double | 收盘价       |
| high              | double | 最高价       |
| low               | double | 最低价       |
| volume            | double | 成交量       |
| day_session_open  | double | 日盘开盘价   |
| limit_up          | double | 涨停价       |
| limit_down        | double | 跌停价       |
| amount            | double | 成交额       |
| open_interest     | double | 累计持仓量   |
| settlement        | double | 结算价       |
| pre_settlement    | double | 昨日结算价   |

财务因子类（仅stock可选）

<div class ="feature-tip">
    注：下述现金流量表、资产负债表、利润表所有字段均含有衍生字段  
</div>

**衍生字段命名规则如下：原字段+\_mrq_n(n为1~12)**  
**表示距离当期查询日的最近前n期（原始字段表示第0期即当期）的财报中的对应字段的值**  
**例：cfs_cash_received_sales_mrq_7表示当期查询日的最近的前第7期的现金流量表中的销售商品、提供劳务收到的现金的值**

现金流量表(cfs)

| 字段                             | 类型   | 描述                               |
|:---------------------------------|:-------|:-----------------------------------|
| cfs_cash_received_sales          | double | 销售商品、提供劳务收到的现金       |
| cfs_tax_refund                   | double | 收到的税费返还                     |
| cfs_net_deposit_inc              | double | 客户存款和同业存放款项净增加额     |
| cfs_net_inc_cb_borr              | double | 向中央银行借款净增加额             |
| cfs_net_inc_oth_fi               | double | 向其他金融机构拆入资金净增加额     |
| cfs_recovery_written_off_loans   | double | 收回已核销贷款                     |
| cfs_cash_received_int_comm       | double | 收取利息、手续费及佣金的现金       |
| cfs_net_inc_dispose_fa           | double | 处置交易性金融资产净增加额         |
| cfs_net_inc_repurchase           | double | 回购业务资金净增加额               |
| cfs_cash_received_orig_ins       | double | 收到原保险合同保费取得的现金       |
| cfs_cash_received_reins          | double | 收到再保业务现金净额               |
| cfs_net_inc_ph_invest            | double | 保户储金及投资款净增加额           |
| cfs_net_inc_borr_capital         | double | 拆入资金净增加额                   |
| cfs_cash_received_proxy_sec      | double | 代理买卖证券收到的现金净额         |
| cfs_cash_received_uw_sec         | double | 代理承销证券收到的现金净额         |
| cfs_cash_oth_operating           | double | 收到其它与经营活动有关的现金       |
| cfs_cash_inflow_operating        | double | 经营活动现金流入小计               |
| cfs_cash_paid_goods              | double | 购买商品、接受劳务支付的现金       |
| cfs_asset_depr_reserve           | double | 资产减值准备                       |
| cfs_fx_effect                    | double | 汇率变动对现金及现金等价物的影响   |
| cfs_oth_affecting_cash           | double | 影响现金及现金等价物的其他科目     |
| cfs_net_inc_cash_equiv           | double | 现金及现金等价物净增加额(主表)     |
| cfs_begin_cash_equiv             | double | 期初现金及现金等价物余额           |
| cfs_end_cash_equiv               | double | 期末现金及现金等价物余额           |
| cfs_cash_paid_employees          | double | 支付给职工以及为职工支付的现金     |
| cfs_cash_paid_taxes              | double | 支付的各项税费                     |
| cfs_net_inc_loans_advances       | double | 客户贷款及垫款净增加额             |
| cfs_net_inc_depos_cb             | double | 存放中央银行和同业款项净增加额     |
| cfs_net_inc_lend_capital         | double | 拆出资金净增加额                   |
| cfs_cash_paid_commissions        | double | 支付手续费及佣金的现金             |
| cfs_cash_paid_orig_ins           | double | 支付原保险合同赔付款项的现金       |
| cfs_cash_paid_reins              | double | 支付再保业务现金净额               |
| cfs_cash_paid_policy_div         | double | 支付保单红利的现金                 |
| cfs_net_inc_trad_fa              | double | 为交易目的而持有的金融资产净增加额 |
| cfs_net_inc_oper_resale          | double | 返售业务资金净增加额(经营)         |
| cfs_cash_paid_oth_operating      | double | 支付其他与经营活动有关的现金       |
| cfs_cash_outflow_operating       | double | 经营活动现金流出小计               |
| cfs_net_cash_operating           | double | 经营活动产生的现金流量净额         |
| cfs_cash_received_dispose_inv    | double | 收回投资收到的现金                 |
| cfs_cash_received_inv_income     | double | 取得投资收益收到的现金             |
| cfs_cash_received_dispose_asset  | double | 处置固定资产等收回的现金净额       |
| cfs_cash_oth_investing           | double | 收到其他与投资活动有关的现金       |
| cfs_cash_inflow_investing        | double | 投资活动现金流入小计               |
| cfs_cash_paid_asset              | double | 购建固定资产等所支付的现金         |
| cfs_cash_paid_invest             | double | 投资支付的现金                     |
| cfs_cash_paid_oth_investing      | double | 支付其他与投资活动有关的现金       |
| cfs_cash_outflow_investing       | double | 投资活动产生的现金流出小计         |
| cfs_net_cash_investing           | double | 投资活动产生的现金流量净额         |
| cfs_cash_received_investors      | double | 吸收投资收到的现金                 |
| cfs_cash_received_minority       | double | 子公司吸收少数股东投资收到的现金   |
| cfs_cash_received_issue_bond     | double | 发行债券收到的现金                 |
| cfs_cash_received_borr           | double | 取得借款收到的现金                 |
| cfs_cash_received_issue_equity   | double | 发行其他权益工具收到的现金         |
| cfs_net_inc_financing_repurchase | double | 回购业务资金净增加额(筹资)         |
| cfs_cash_oth_financing           | double | 收到其他与筹资活动有关的现金       |
| cfs_cash_inflow_financing        | double | 筹资活动现金流入小计               |
| cfs_cash_paid_debt               | double | 偿还债务支付的现金                 |
| cfs_cash_paid_div_interest       | double | 分配股利、利润或偿付利息支付的现金 |
| cfs_div_paid_minority            | double | 子公司支付给少数股东的股利等       |
| cfs_cash_paid_oth_financing      | double | 支付其他与筹资活动有关的现金       |
| cfs_cash_outflow_financing       | double | 筹资活动现金流出小计               |
| cfs_net_cash_financing           | double | 筹资活动产生的现金流量净额         |
| cfs_net_cash_dispose_sub         | double | 处置子公司收到的现金净额           |
| cfs_net_cash_acquire_sub         | double | 取得子公司支付的现金净额           |
| cfs_net_inc_pledge_loans         | double | 质押贷款净增加额                   |
| cfs_net_inc_invest_resale        | double | 返售业务资金净增加额(投资)         |
| cfs_net_inc_cash_equiv_note      | double | 现金及现金等价物净增加额(附注)     |
| cfs_fix_asset_depr               | double | 固定资产折旧                       |
| cfs_defer_exp_amort              | double | 长期待摊费用摊销                   |
| cfs_intan_asset_amort            | double | 无形资产摊销                       |

资产负债表(bs)

| 字段                          | 类型   | 描述                         |
|:------------------------------|:-------|:-----------------------------|
| bs_trad_asset                 | double | 交易性金融资产               |
| bs_money_cap                  | double | 货币资金                     |
| bs_client_depos               | double | 客户资金存款                 |
| bs_notes_receive              | double | 应收票据                     |
| bs_div_receive                | double | 应收股利                     |
| bs_notes_accts_receiv         | double | 应收票据及应收账款           |
| bs_int_receive                | double | 应收利息                     |
| bs_bad_debt_reserve           | double | 坏账准备                     |
| bs_net_accts_receive          | double | 应收账款净额                 |
| bs_contract_assets            | double | 合同资产                     |
| bs_prepayment                 | double | 预付账款                     |
| bs_receiv_financing           | double | 应收款项融资                 |
| bs_lease_receive              | double | 应收融资租赁款               |
| bs_oth_eq_invest              | double | 其他权益工具投资             |
| bs_oth_illiq_fa               | double | 其他非流动金融资产           |
| bs_nca_within_1y              | double | 一年内到期的非流动资产       |
| bs_oth_receiv_int_div         | double | 其他应收款(含利息和股利)     |
| bs_inventory                  | double | 存货                         |
| bs_consumable_bio_assets      | double | 消耗性生物资产               |
| bs_amor_exp                   | double | 待摊费用                     |
| bs_hfs_assets                 | double | 划分为持有待售的资产         |
| bs_contract_work              | double | 工程施工                     |
| bs_oth_cur_assets             | double | 其他流动资产                 |
| bs_total_cur_assets           | double | 流动资产合计                 |
| bs_fa_avail_sale              | double | 可供出售金融资产             |
| bs_ncl_due_1y                 | double | 一年内到期的非流动负债       |
| bs_debt_invest                | double | 债权投资                     |
| bs_oth_debt_invest            | double | 其他债权投资                 |
| bs_htm_invest                 | double | 持有至到期投资               |
| bs_invest_real_estate         | double | 投资性房地产                 |
| bs_lt_rec                     | double | 长期应收款                   |
| bs_net_lt_eqt_invest          | double | 长期股权投资净额             |
| bs_accu_depr                  | double | 累计折旧                     |
| bs_fix_asset_impair           | double | 固定资产减值准备             |
| bs_net_fix_assets             | double | 固定资产净额                 |
| bs_total_fix_assets           | double | 固定资产合计                 |
| bs_const_materials            | double | 工程物资                     |
| bs_cip                        | double | 在建工程                     |
| bs_cip_total                  | double | 在建工程合计                 |
| bs_fix_assets_disp            | double | 固定资产清理                 |
| bs_prod_bio_assets            | double | 生产性生物资产               |
| bs_oil_gas_assets             | double | 油气资产                     |
| bs_intan_assets               | double | 无形资产                     |
| bs_transac_seat_fee           | double | 交易席位费                   |
| bs_r_and_d                    | double | 开发支出                     |
| bs_use_right_assets           | double | 使用权资产                   |
| bs_goodwill                   | double | 商誉                         |
| bs_lt_amor_exp                | double | 长期待摊费用                 |
| bs_defer_tax_assets           | double | 递延所得税资产               |
| bs_oth_nca                    | double | 其他非流动资产               |
| bs_total_nca                  | double | 非流动资产合计               |
| bs_invest_as_receive          | double | 应收款项类投资               |
| bs_lending_funds              | double | 融出资金                     |
| bs_reinsur_reserve_receive    | double | 应收分保合同准备金           |
| bs_sett_reserve               | double | 结算备付金                   |
| bs_client_prov                | double | 客户备付金                   |
| bs_depos_oth_bfi              | double | 存放同业款项                 |
| bs_prec_metals                | double | 贵金属                       |
| bs_loan_to_oth_bank_fi        | double | 拆出资金                     |
| bs_deriv_assets               | double | 衍生金融资产                 |
| bs_pur_resale_fa              | double | 买入返售金融资产             |
| bs_decr_in_disbur             | double | 发放贷款和垫款               |
| bs_premium_receive            | double | 应收保费                     |
| bs_subrogation_receive        | double | 应收代位追偿款               |
| bs_reinsur_receive            | double | 应收分保账款                 |
| bs_rr_reins_une_prem          | double | 应收分保未到期责任准备金     |
| bs_rr_reins_outstd_cla        | double | 应收分保未决赔款准备金       |
| bs_rr_reins_lins_liab         | double | 应收分保寿险责任准备金       |
| bs_rr_reins_lthins_liab       | double | 应收分保长期健康险责任准备金 |
| bs_ph_pledge_loans            | double | 保户质押贷款                 |
| bs_time_deposits              | double | 定期存款                     |
| bs_refund_depos               | double | 存出保证金                   |
| bs_refund_cap_depos           | double | 存出资本保证金               |
| bs_indep_acct_assets          | double | 独立账户资产                 |
| bs_oth_assets                 | double | 其他资产                     |
| bs_oth_receive                | double | 其他应收款(原值)             |
| bs_total_assets               | double | 总资产                       |
| bs_pledge_borr                | double | 质押借款                     |
| bs_st_borr                    | double | 短期借款                     |
| bs_trading_fl                 | double | 交易性金融负债               |
| bs_notes_payable              | double | 应付票据                     |
| bs_acct_payable               | double | 应付账款                     |
| bs_accounts_pay               | double | 应付票据及应付账款           |
| bs_contract_liab              | double | 合同负债                     |
| bs_adv_receipts               | double | 预收账款                     |
| bs_payroll_payable            | double | 应付职工薪酬                 |
| bs_div_payable                | double | 应付股利                     |
| bs_taxes_payable              | double | 应交税费                     |
| bs_int_payable                | double | 应付利息                     |
| bs_oth_fees_payable           | double | 其他应交款                   |
| bs_oth_payable                | double | 其他应付款                   |
| bs_oth_payable_int_div        | double | 其他应付款(含利息和股利)     |
| bs_st_bonds_payable           | double | 应付短期债券                 |
| bs_acc_exp                    | double | 预提费用                     |
| bs_hfs_sales                  | double | 划分为持有待售的负债         |
| bs_estimated_liab             | double | 预计负债                     |
| bs_deferred_inc               | double | 递延收益                     |
| bs_non_cur_liab_due_1y        | double | 一年内到期的非流动负债       |
| bs_oth_cur_liab               | double | 其他流动负债                 |
| bs_total_cur_liab             | double | 流动负债合计                 |
| bs_lt_borr                    | double | 长期借款                     |
| bs_bond_payable               | double | 应付债券                     |
| bs_pref_shares                | double | 优先股                       |
| bs_perpetual_bond             | double | 永续债(应付债券)             |
| bs_lt_payable                 | double | 长期应付款                   |
| bs_lt_payroll_payable         | double | 长期应付职工薪酬             |
| bs_specific_payables          | double | 专项应付款                   |
| bs_housing_revolving          | double | 住房周转金                   |
| bs_defer_tax_liab             | double | 递延所得税负债               |
| bs_lease_liab                 | double | 租赁负债                     |
| bs_fin_lease_payable          | double | 应付融资租赁款               |
| bs_oth_ncl                    | double | 其他非流动负债               |
| bs_total_ncl                  | double | 非流动负债合计               |
| bs_cb_borr                    | double | 向中央银行借款               |
| bs_depos_ib_deposits          | double | 同业及其他金融机构存放款项   |
| bs_loan_oth_bank              | double | 拆入资金                     |
| bs_deriv_liab                 | double | 衍生金融负债                 |
| bs_sold_for_repur_fa          | double | 卖出回购金融资产款           |
| bs_depos                      | double | 吸收存款                     |
| bs_acting_trading_sec         | double | 代理买卖证券款               |
| bs_acting_uw_sec              | double | 代理承销证券款               |
| bs_depos_received             | double | 存入保证金                   |
| bs_prem_receiv_adva           | double | 预收保费                     |
| bs_comm_payable               | double | 应付手续费及佣金             |
| bs_payable_to_reinsurer       | double | 应付分保账款                 |
| bs_indem_payable              | double | 应付赔付款                   |
| bs_policy_div_payable         | double | 应付保单红利                 |
| bs_depos_oth_bfi              | double | 吸收存款及同业存款           |
| bs_reserve_insur_cont         | double | 保险合同准备金               |
| bs_ph_invest                  | double | 保户储金及投资款             |
| bs_reserve_une_prem           | double | 未到期责任准备金             |
| bs_reserve_outstd_claims      | double | 未决赔款准备金               |
| bs_reserve_lins_liab          | double | 寿险责任准备金               |
| bs_reserve_lthins_liab        | double | 长期健康险责任准备金         |
| bs_indep_acct_liab            | double | 独立账户负债                 |
| bs_oth_liab                   | double | 其他负债                     |
| bs_defer_inc_non_cur_liab     | double | 递延收益(长期负债)           |
| bs_total_liab                 | double | 负债合计                     |
| bs_cap_stk                    | double | 实收资本(或股本)             |
| bs_oth_eqt_tools              | double | 其他权益工具                 |
| bs_oth_eqt_tools_p_shr        | double | 权益部分的优先股             |
| bs_perpetual_equity_debt      | double | 永续债(其他权益工具)         |
| bs_cap_reserve                | double | 资本公积金                   |
| bs_surplus_reserve            | double | 盈余公积                     |
| bs_undistr_profit             | double | 未分配利润                   |
| bs_treasury_share             | double | 减:库存股                    |
| bs_total_hldr_eqy_exc_min_int | double | 归属于母公司所有者权益合计   |
| bs_total_hldr_eqy_inc_min_int | double | 股东权益合计                 |
| bs_ordin_risk_reserve         | double | 一般风险准备                 |
| bs_trade_risk_allow           | double | 交易风险准备                 |
| bs_forex_diff                 | double | 外币报表折算差额             |
| bs_invest_loss_unconf         | double | 未确认投资损失               |
| bs_oth_reserves               | double | 其他储备                     |
| bs_special_reserve            | double | 专项储备                     |
| bs_minority_int               | double | 少数股东权益                 |
| bs_total_liab_hldr_eqy        | double | 负债和股东权益总计           |

利润表(is)

| 字段                        | 类型   | 描述                         |
|:----------------------------|:-------|:-----------------------------|
| is_total_revenue            | double | 营业总收入                   |
| is_revenue                  | double | 营业收入                     |
| is_net_interest_inc         | double | 利息净收入                   |
| is_n_commis_income          | double | 手续费及佣金净收入           |
| is_comm_income              | double | 手续费及佣金收入             |
| is_comm_exp                 | double | 手续费及佣金支出             |
| is_n_sec_tb_income          | double | 代理买卖证券业务净收入       |
| is_n_sec_uw_income          | double | 证券承销业务净收入           |
| is_n_asset_mg_income        | double | 受托客户资产管理业务净收入   |
| is_prem_earned              | double | 已赚保费                     |
| is_prem_income              | double | 保险业务收入                 |
| is_reins_income             | double | 分保费收入                   |
| is_out_prem                 | double | 减:分出保费                  |
| is_une_prem_reserve         | double | 提取未到期责任准备金         |
| is_total_cogs               | double | 营业总成本                   |
| is_oper_exp                 | double | 营业支出(金融类)             |
| is_prem_refund              | double | 退保金                       |
| is_compensation_payout      | double | 赔付支出                     |
| is_compensation_payout_refu | double | 减:摊回赔付支出              |
| is_reserve_insur_liab       | double | 提取保险责任准备金           |
| is_insur_reserve_refu       | double | 减:摊回保险责任准备金        |
| is_div_payt                 | double | 保单红利支出                 |
| is_reins_exp                | double | 分保费用                     |
| is_oth_b_income             | double | 其他经营收入                 |
| is_other_bus_cost           | double | 其他经营成本                 |
| is_rd_exp                   | double | 研发费用                     |
| is_n_oth_income             | double | 非经营性净收益               |
| is_net_expo_hedging         | double | 净敞口套期收益               |
| is_oth_income               | double | 其他收益                     |
| is_credit_impair_loss       | double | 信用资产减值损失             |
| is_oper_admin_exp           | double | 业务及管理费用               |
| is_reins_cost_refund        | double | 减:摊回分保费用              |
| is_insur_comm_exp           | double | 保险手续费及佣金支出         |
| is_asset_disp_income        | double | 资产处置收益                 |
| is_oper_cost                | double | 营业成本                     |
| is_biz_tax_surchg           | double | 营业税                       |
| is_gross_profit             | double | 主营业务利润                 |
| is_sell_exp                 | double | 销售费用                     |
| is_admin_exp                | double | 管理费用                     |
| is_fin_exp                  | double | 财务费用                     |
| is_fin_exp_int_inc          | double | 利息收入(财务费用)           |
| is_fin_exp_int_exp          | double | 利息支出(财务费用)           |
| is_forex_gain               | double | 兑汇损益                     |
| is_operate_profit           | double | 营业利润                     |
| is_ass_invest_income        | double | 对联营合营企业的投资收益     |
| is_fv_value_chg_gain        | double | 公允价值变动净收益           |
| is_invest_income            | double | 投资收益                     |
| is_assets_impair_loss       | double | 资产减值损失                 |
| is_int_income               | double | 利息收入                     |
| is_int_exp                  | double | 利息支出                     |
| is_non_oper_income          | double | 营业外收入                   |
| is_non_oper_exp             | double | 营业外支出                   |
| is_nca_disploss             | double | 非流动资产处置净损失         |
| is_oth_affecting_tp         | double | 影响利润总额的其他科目       |
| is_total_profit             | double | 利润总额                     |
| is_income_tax               | double | 所得税                       |
| is_invest_loss_unconf       | double | 未确认的投资损失             |
| is_oth_affecting_np         | double | 影响净利润的其他科目         |
| is_n_income                 | double | 净利润                       |
| is_non_recurring_pnl        | double | 非经常性损益                 |
| is_net_after_nr             | double | 扣除非经常性损益后的净利润   |
| is_class_continuity         | double | 按经营持续性分类             |
| is_continued_net_profit     | double | 持续经营净利润               |
| is_end_net_profit           | double | 终止经营净利润               |
| is_class_ownership          | double | 按所有权归属分类             |
| is_n_income_attr_p          | double | 归属母公司净利润             |
| is_minority_gain            | double | 少数股东损益                 |
| is_oth_compr_income         | double | 其他综合收益                 |
| is_oci_unclassified         | double | 以后不能重分类进损益表的OCI  |
| is_remeasured_oci           | double | 重新计量设定收益计划变动     |
| is_oci_equity_unclass       | double | 权益法下不能重分类的OCI份额  |
| is_oth_eqt_instruments_chg  | double | 其他权益工具投资公允价值变动 |
| is_corp_credit_risk_chg     | double | 企业自身信用风险公允价值变动 |
| is_oci_classified           | double | 以后能重分类进损益表的OCI    |
| is_oci_equity_class         | double | 权益法下能重分类的OCI份额    |
| is_fa_avail_sale_chg        | double | 可供出售金融资产公允价值变动 |
| is_htm_reclass_chg          | double | 持有至到期投资重分类损益     |
| is_cf_hedging_effective     | double | 现金流量套期损益的有效部分   |
| is_forex_stmt_diff          | double | 外币财务报表折算差额         |
| is_oth_oci                  | double | 其他OCI                      |
| is_oth_debt_invest_chg      | double | 其他债权投资公允价值变动     |
| is_assets_reclass_oci       | double | 金融资产重分类计入OCI        |
| is_oth_debt_invest_reserve  | double | 其他债权投资信用减值准备     |
| is_oci_minority             | double | 归属于少数股东的OCI          |
| is_t_compr_income           | double | 综合收益总额                 |
| is_compr_inc_attr_p         | double | 归属于母公司的综合收益总额   |
| is_compr_inc_attr_m_s       | double | 归属于少数股东的综合收益总额 |
| is_basic_eps                | double | 基本每股收益                 |
| is_diluted_eps              | double | 稀释每股收益                 |
| is_adj_asset_impair         | double | 资产减值损失(调整项)         |
| is_adj_credit_impair        | double | 信用减值损失(调整项)         |

估值(ratio)

| 字段                      | 类型   | 描述                      |
|:--------------------------|:-------|:--------------------------|
| ratio_pe_lyr              | double | 市盈率lyr                 |
| ratio_pe_ttm              | double | 市盈率ttm                 |
| ratio_ep_lyr              | double | 盈市率lyr                 |
| ratio_ep_ttm              | double | 盈市率ttm                 |
| ratio_pcf_total_lyr       | double | 市现率_总现金流lyr        |
| ratio_pcf_total_ttm       | double | 市现率_总现金流ttm        |
| ratio_pcf_ocf_lyr         | double | 市现率_经营lyr            |
| ratio_pcf_ocf_ttm         | double | 市现率_经营ttm            |
| ratio_cfp_lyr             | double | 现金收益率lyr             |
| ratio_cfp_ttm             | double | 现金收益率ttm             |
| ratio_pb_lyr              | double | 市净率lyr                 |
| ratio_pb_ttm              | double | 市净率ttm                 |
| ratio_pb_lf               | double | 市净率lf                  |
| ratio_bm_lyr              | double | 账面市值比lyr             |
| ratio_bm_ttm              | double | 账面市值比ttm             |
| ratio_bm_lf               | double | 账面市值比lf              |
| ratio_div_yield_ttm       | double | 股息率ttm                 |
| ratio_peg_lyr             | double | PEG值lyr                  |
| ratio_peg_ttm             | double | PEG值ttm                  |
| ratio_ps_lyr              | double | 市销率lyr                 |
| ratio_ps_ttm              | double | 市销率ttm                 |
| ratio_sp_lyr              | double | 销售收益率lyr             |
| ratio_sp_ttm              | double | 销售收益率ttm             |
| ratio_market_cap_float    | double | 流通股总市值              |
| ratio_market_cap_total    | double | 总市值                    |
| ratio_a_share_mv          | double | A股市值                   |
| ratio_a_share_mv_float    | double | 流通A股市值               |
| ratio_ev_lyr              | double | 企业价值lyr               |
| ratio_ev_ttm              | double | 企业价值ttm               |
| ratio_ev_lf               | double | 企业价值lf                |
| ratio_ev_no_cash_lyr      | double | 企业价值(不含货币资金)lyr |
| ratio_ev_no_cash_ttm      | double | 企业价值(不含货币资金)ttm |
| ratio_ev_no_cash_lf       | double | 企业价值(不含货币资金)lf  |
| ratio_ev_ebitda_lyr       | double | 企业倍数lyr               |
| ratio_ev_ebitda_ttm       | double | 企业倍数ttm               |
| ratio_ev_no_cash_ebit_lyr | double | 企业倍数(不含货币资金)lyr |
| ratio_ev_no_cash_ebit_ttm | double | 企业倍数(不含货币资金)ttm |

**5.4. 使用示例**

**5.4.1. 获取单支股票的部分回测因子**

```python
import panda_data
result = panda_data.get_factor(
    symbol="000001.SZ",
    start_date="20250101",
    end_date="20250131",
    factors=['open', 'close'],
    index_component="100",
    type="stock"
)
print(result)
```

```text
date symbol open close index_component
0 20250127 000001.SZ 1923.31104 1938.52176 100
1 20250124 000001.SZ 1913.17056 1916.55072 100
2 20250123 000001.SZ 1887.81936 1913.17056 100
3 20250122 000001.SZ 1913.17056 1874.29872 100
4 20250121 000001.SZ 1935.14160 1914.86064 100
5 20250120 000001.SZ 1943.59200 1930.07136 100
6 20250117 000001.SZ 1948.66224 1935.14160 100
7 20250116 000001.SZ 1952.04240 1955.42256 100
8 20250115 000001.SZ 1923.31104 1940.21184 100
9 20250114 000001.SZ 1892.88960 1923.31104 100
10 20250113 000001.SZ 1901.34000 1892.88960 100
11 20250110 000001.SZ 1926.69120 1909.79040 100
12 20250109 000001.SZ 1943.59200 1926.69120 100
13 20250108 000001.SZ 1943.59200 1943.59200 100
14 20250107 000001.SZ 1930.07136 1945.28208 100
15 20250106 000001.SZ 1923.31104 1933.45152 100
16 20250103 000001.SZ 1933.45152 1923.31104 100
17 20250102 000001.SZ 1982.46384 1931.76144 100
```

**5.4.2. 获取多个期货的部分回测因子**

```python
import panda_data
result = panda_data.get_factor(
    symbol=["A_DOMINANT.DCE", "ZN2501.SHF"],
    start_date="20250101",
    end_date="20250131",
    factors=['open', 'close'],
    index_component="100",
    type="future"
)
print(result)
```

```text
date symbol open close
0 20250127 A_DOMINANT.DCE 4026.0 4026.0
1 20250124 A_DOMINANT.DCE 4019.0 4032.0
2 20250123 A_DOMINANT.DCE 4057.0 4013.0
3 20250122 A_DOMINANT.DCE 4041.0 4060.0
4 20250121 A_DOMINANT.DCE 4025.0 4032.0
5 20250120 A_DOMINANT.DCE 4029.0 4019.0
6 20250117 A_DOMINANT.DCE 3998.0 4028.0
7 20250116 A_DOMINANT.DCE 3984.0 4000.0
8 20250115 A_DOMINANT.DCE 3950.0 3987.0
9 20250114 A_DOMINANT.DCE 3938.0 3962.0
10 20250113 A_DOMINANT.DCE 3878.0 3937.0
11 20250109 A_DOMINANT.DCE 3837.0 3840.0
12 20250108 A_DOMINANT.DCE 3847.0 3837.0
13 20250107 A_DOMINANT.DCE 3901.0 3848.0
14 20250106 A_DOMINANT.DCE 3910.0 3892.0
15 20250103 A_DOMINANT.DCE 3942.0 3917.0
16 20250102 A_DOMINANT.DCE 3929.0 3931.0
17 20250115 ZN2501.SHF 24395.0 24250.0
18 20250114 ZN2501.SHF 24495.0 24450.0
19 20250113 ZN2501.SHF 24335.0 24495.0
20 20250109 ZN2501.SHF 24300.0 24360.0
21 20250108 ZN2501.SHF 24580.0 24415.0
22 20250107 ZN2501.SHF 24875.0 24620.0
23 20250106 ZN2501.SHF 24850.0 24710.0
24 20250103 ZN2501.SHF 25390.0 24980.0
25 20250102 ZN2501.SHF 25650.0 25600.0
```

**6. 获取复权因子**

**6.1. 方法名：get_adj_factor**

**6.2. 入参**

| 字段 | 类型 | 描述 | 是否必填 |
|:---|:---|:---|:---|
| symbol | Optional\[Union\[str, List\[str\]\]\] | 股票代码 | 非必填 |
| start_date | Optional\[str\] | 开始日期,eg:"20250702" | 非必填 |
| end_date | Optional\[str\] | 结束日期,eg:"20250702" | 非必填 |
| fields | Optional\[Union\[str, List\[str\]\]\] | 返回字段列表 | 非必填 |

**6.3. 响应参数**

| 字段              | 类型   | 描述         |
|:------------------|:-------|:-------------|
| symbol            | str    | 股票代码     |
| ex_date           | str    | 除权除息日期 |
| ex_cum_factor     | double | 前复权因子   |
| ex_factor         | double | 后复权因子   |
| ex_end_date       | str    | 除权结束日期 |
| announcement_date | str    | 公告日期     |

**6.4. 使用示例**

**6.4.1. 获取一定日期内某只股票的复权因子**

```python
import panda_data
result = panda_data.get_adj_factor(
    symbol="000001.SZ",
    start_date="20250101",
    end_date="20250831",
    fields=[]
)
print(result)
```

```text
symbol ex_date announcement_date ex_cum_factor ex_end_date ex_factor
0 000001.SZ 20250612 20250611 174.334 NaN 1.031513
```

**6.4.2. 获取一定日期内全部股票的复权因子并使用fields**

```python
import panda_data
result = panda_data.get_adj_factor(
    symbol="",
    start_date="20250101",
    end_date="20250831",
    fields=["symbol", "ex_date", "announcement_date", "ex_cum_factor"]
)
print(result)
```

```text
symbol ex_date announcement_date ex_cum_factor
0 000001.SZ 20250612 20250611 174.334000
1 000009.SZ 20250827 20250826 12.017100
2 000019.SZ 20250617 20250616 5.634970
3 000021.SZ 20250611 20250610 14.227600
4 000025.SZ 20250528 20250527 2.768860
... ... ... ... ...
3553 688798.SH 20250520 20250519 1.413086
3554 688799.SH 20250529 20250528 1.513119
3555 688800.SH 20250530 20250529 1.855447
3556 688819.SH 20250613 20250612 1.093522
3557 689009.SH 20250613 20250612 1.026022
```

