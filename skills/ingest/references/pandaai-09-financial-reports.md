---
source: https://www.pandaai.online/knowledge-base/?pageUrl=/coreFeatrue&id=%E4%BA%94%E6%95%B0%E6%8D%AEapi
title: PandaAI Data API - Financial Forecasts, Performance, Reports, and Audit Opinion
extracted: 2026-05-06
source_lines: 2938-3621
---

## 财务与因子

**1. 获取业绩预告数据**

**1.1. 方法名：get_fina_forecast**

**1.2. 入参**

| 字段 | 类型 | 描述 | 是否必填 |
|:---|:---|:---|:---|
| symbol | Optional\[Union\[str, List\[str\]\]\] | 股票代码，可以是单个字符串或字符串列表 | 非必填 |
| fields | Optional\[Union\[str, List\[str\]\]\] | 需要返回的字段列表 | 非必填 |
| info_date | Optional\[str\] | 信息发布日期，格式为 "YYYYMMDD" | 非必填 |
| end_quarter | Optional\[str\] | 报告季度，格式为 "YYYYqN" | 非必填 |

**1.3. 响应参数**

| 字段                          | 类型   | 描述               |
|:------------------------------|:-------|:-------------------|
| symbol                        | str    | 股票代码           |
| info_date                     | str    | 信息发布日期       |
| end_date                      | str    | 报告日期           |
| forecast_type                 | str    | 整体业绩预期       |
| forecast_description          | str    | 业绩预期时间段描述 |
| forecast_growth_rate_floor    | double | 最小预期增长幅度   |
| forecast_growth_rate_ceiling  | double | 最大预期增长幅度   |
| forecast_earning_floor        | double | 最小预期收入       |
| forecast_earning_ceiling      | double | 最大预期收入       |
| forecast_np_floor             | double | 最小预期净利润     |
| forecast_np_ceiling           | double | 最大预期净利润     |
| forecast_eps_floor            | double | 最小预期每股       |
| forecast_eps_ceiling          | double | 最大预期每股收益   |
| net_profit_yoy_const_forecast | double | 一致预期净利润增幅 |

**1.4. 使用示例**

**1.4.1. 获取一定日期后某只股票的业绩预告数据**

```python
import panda_data
result = panda_data.get_fina_forecast(
    symbol="688795.SH",
    info_date="20251128",
    end_quarter="2025q4",
    fields=[]
)
print(result)
```

```text
symbol info_date ... forecast_type net_profit_yoy_const_forecast
0 688795.SH 20251128 ... 减亏 None
```

**1.4.2. 获取一定日期后某只股票的业绩预告且使用fields**

```python
import panda_data
result = panda_data.get_fina_forecast(
    symbol="688795.SH",
    info_date="20251128",
    end_quarter="2025q4",
    fields=["symbol", "info_date", "end_date", "report_type",
        "forecast_description", "forecast_growth_rate_ceiling", "forecast_type"]
    )
    print(result)
```

```text
symbol info_date ... forecast_growth_rate_ceiling forecast_type
0 688795.SH 20251128 ... 54.89 减亏
```

**2. 获取财务快报数据**

**2.1. 方法名：get_fina_performance**

**2.2. 入参**

| 字段 | 类型 | 描述 | 是否必填 |
|:---|:---|:---|:---|
| symbol | Optional\[Union\[str, List\[str\]\]\] | 股票代码，可以是单个字符串或字符串列表 | 非必填 |
| fields | Optional\[Union\[str, List\[str\]\]\] | 需要返回的字段列表 | 非必填 |
| info_date | Optional\[str\] | 信息发布日期，格式为 "YYYYMMDD" | 非必填 |
| end_quarter | Optional\[str\] | 报告季度，格式为 "YYYYqN" | 非必填 |

**2.3. 响应参数**

| 字段                                | 类型   | 描述                            |
|:------------------------------------|:-------|:--------------------------------|
| symbol                              | str    | 股票代码                        |
| info_date                           | str    | 信息发布日期                    |
| end_date                            | str    | 报告日期                        |
| operating_revenue                   | double | 营业收入或主营业务收入(元)      |
| gross_profit                        | double | 主营业务利润(元)                |
| operating_profit                    | double | 营业利润(元)                    |
| total_profit                        | double | 利润总额(元)                    |
| np_parent_owners                    | double | 归属母公司净利润(元)            |
| net_profit_cut                      | double | 扣除非经常性损益后净利润(元)    |
| net_operate_cashflow                | double | 经营活动现金流量净额(元)        |
| total_assets                        | double | 总资产(元)                      |
| se_without_minority                 | double | 归属母公司普通股东权益(元)      |
| se_parent_owners                    | double | 归属母公司股东权益(元)          |
| total_shares                        | double | 总股本(股)                      |
| basic_eps                           | double | 基本每股收益                    |
| eps_weighted                        | double | 每股收益(加权)(元)              |
| eps_cut_epscut                      | double | 每股收益(扣除)(元)              |
| eps_cut_weighted                    | double | 每股收益(扣除加权)(元)          |
| roe                                 | double | 净资产收益率(摊薄)(%)           |
| roe_weighted                        | double | 净资产收益率(加权)(%)           |
| roe_cut                             | double | 净资产收益率(扣除摊薄)(%)       |
| roe_cut_weighted                    | double | 净资产收益率(扣除加权)(%)       |
| net_operate_cashflow_per_share      | double | 每股经营活动现金流量净额(元)    |
| equity_per_share                    | double | 每股净资产(元)                  |
| operating_revenue_yoy               | double | 主营业务收入同比(%)             |
| gross_profit_yoy                    | double | 主营业务利润同比(%)             |
| operating_profit_yoy                | double | 营业利润同比(%)                 |
| total_profit_yoy                    | double | 利润总额同比(%)                 |
| np_parent_minority_pany_yoy         | double | 归属母公司净利润同比(%)         |
| ne_t_minority_ty_yoy                | double | 扣除非经常性损益后净利润同比(%) |
| net_operate_cash_flow_yoy           | double | 经营活动现金流量净额同比(%)     |
| total_assets_to_opening             | double | 总资产较期初比(%)               |
| se_without_minority_to_opening      | double | 归属母公司股东权益较期初比(%)   |
| basic_eps_yoy                       | double | 每股收益(摊薄) 同比(%)          |
| eps_weighted_yoy                    | double | 每股收益(加权) 同比(%)          |
| eps_cut_yoy                         | double | 每股收益(扣除) 同比(%)          |
| eps_cut_weighted_yoy                | double | 每股收益(扣除加权) 同比(%)      |
| roe_yoy                             | double | 净资产收益率(摊薄) 同比(%)      |
| roe_weighted_yoy                    | double | 净资产收益率(加权) 同比(%)      |
| roe_cut_yoy                         | double | 净资产收益率(扣除摊薄) 同比(%)  |
| roe_cut_weighted_yoy                | double | 净资产收益率(扣除加权) 同比(%)  |
| net_operate_cash_flow_per_share_yoy | double | 每股经营活动现金流量净额同比(%) |
| net_asset_psto_opening              | double | 每股净资产较期初比(%)           |

**2.4. 使用示例**

**2.4.1. 获取一定日期内某只股票的财务快报数据**

```python
import panda_data
result = panda_data.get_fina_performance(
    info_date="20251107",
    symbol="688235.SH",
    end_quarter="2025q4",
    fields=[]
)
print(result)
```

```text
info_date symbol basic_eps ... total_profit total_profit_yoy total_shares
0 20251107 688235.SH 0.81 ... 1.543219e+09 145.23766 None
```

**2.4.2. 获取一定日期内某只股票的财务快报数据且使用fields**

```python
import panda_data
result = panda_data.get_fina_performance(
    info_date="20251107",
    symbol="688235.SH",
    end_quarter="2025q4",
    fields=["symbol", "info_date", "end_date", "basic_eps", "eps_cut_epscut",
        "ne_t_minority_ty_yoy", "np_parent_owners"]
    )
    print(result)
```

```text
info_date symbol ... ne_t_minority_ty_yoy np_parent_owners
0 20251107 688235.SH ... 124.295951 1.138596e+09
```

**3. 获取财务季度报告**

**3.1. 方法名：get_fina_reports**

**3.2. 入参**

| 字段 | 类型 | 描述 | 是否必填 |
|:---|:---|:---|:---|
| symbol | Optional\[Union\[str, list\]\] | 股票名称 | 非必填 |
| start_quarter | Optional\[str\] | 起始季度，格式为 "YYYYqN"（与end_quarter同用，end_quarter启用时必填） | 非必填 |
| end_quarter | Optional\[str\] | 结束季度，格式为 "YYYYqN"（与start_quarter同用，start_quarter启用时必填） | 非必填 |
| date | Optional\[str\] | 公告日期,返回该日期及之前的数据（当start_date和end_date均不启用时此字段必填） | 非必填 |
| is_latest | Optional\[bool\] | True：返回最新披露数据，False：返回全部。默认为True | 非必填 |
| fields | Optional\[Union\[str, list\]\] | 返回字段 | 非必填 |

**3.3. 响应参数**

**3.3.1. 响应参数**

| 字段        | 类型   | 描述                                   |
|:------------|:-------|:---------------------------------------|
| symbol      | str    | 股票代码                               |
| fields      | double | 需要返回的财务字段(见数据库设计)       |
| quarter     | str    | 季度                                   |
| if_adjusted | int    | 是否为当期财报数据，0为当期，1为非当期 |

以下为财务相关字段

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

**3.4. 使用示例**

**3.4.1. 获取一定季度内某只股票的财务季度报告**

```python
import panda_data
result = panda_data.get_fina_reports(
    symbol="688795.SH",
    date="20251114",
    start_quarter="2024q1",
    end_quarter="2026q1",
    is_latest=False,
    fields=[]
)
print(result)
```

```text
symbol quarter date ... is_une_prem_reserve bs_rr_reins_une_prem bs_use_right_assets
0 688795.SH 2024q4 20250630 ... None None 17260038.22
1 688795.SH 2024q4 20250905 ... None None 17260000.00
2 688795.SH 2025q2 20250905 ... None None 19931500.00
3 688795.SH 2024q4 20250919 ... None None 17260038.22
4 688795.SH 2025q2 20250919 ... None None 19931513.58
5 688795.SH 2024q4 20250926 ... None None 17260038.22
6 688795.SH 2025q2 20250926 ... None None 19931513.58
7 688795.SH 2024q4 20251030 ... None None 17260038.22
8 688795.SH 2025q2 20251030 ... None None 19931513.58
9 688795.SH 2024q2 20251114 ... None None NaN
10 688795.SH 2024q3 20251114 ... None None NaN
11 688795.SH 2024q4 20251114 ... None None 17260038.22
12 688795.SH 2025q2 20251114 ... None None 19931513.58
13 688795.SH 2025q3 20251114 ... None None 19234252.47
```

**3.4.2. 获取一定季度内某只股票的最新财务季度报告且使用fields**

```python
import panda_data
result = panda_data.get_fina_reports(
    symbol="688795.SH",
    date="20251114",
    start_quarter="2024q1",
    end_quarter="2026q1",
    is_latest=True,
    fields=["symbol", "date", "quarter", "adjust_credit_asset_impairment", "accts_payable",
        "cash_from_operating_activities", "cash_from_other_operating_activities"]
    )
    print(result)
```

```text
symbol quarter date bs_acct_payable is_adj_credit_impair cfs_cash_inflow_operating cfs_cash_oth_operating
0 688795.SH 2024q2 20251114 None None None None
```

**4. 获取财务报告审计意见**

**4.1. 方法名：get_audit_opinion**

**4.2. 入参**

| 字段 | 类型 | 描述 | 是否必填 |
|:---|:---|:---|:---|
| symbol | Optional\[Union\[str, List\[str\]\]\] | 股票代码 | 非必填 |
| start_quarter | Optional\[str\] | 开始季度,eg:"2025q1" | 非必填 |
| end_quarter | Optional\[str\] | 结束季度,eg:"2025q3" | 非必填 |
| fields | Optional\[Union\[str, List\[str\]\]\] | 返回字段列表 | 非必填 |
| market | Optional\[str\] | 市场,默认'cn'为中国内地市场 | 非必填 |

**4.3. 响应参数**

| 字段       | 类型 | 描述               |
|:-----------|:-----|:-------------------|
| date       | str  | 公告发布日         |
| symbol     | str  | 股票代码           |
| quarter    | str  | 报告季度           |
| audit_type | str  | 审计报告类型       |
| agency     | str  | 会计师事务所       |
| opinion    | str  | 审计意见（见下表） |

审计意见类型表:

|  |  |
|:---|:---|
| opinion | 描述 |
| unqualified_opinion | 无保留意见 |
| unqualified_opinion_with_emphasis-of-matter_paragraph | 无保留意见并带解释性说明 |
| qualified_opinion | 保留意见 |
| qualified_opinion_with_basis_for_qualification_paragraph | 保留意见并带解释性说明 |
| disclaimer_of_opinion | 拒绝/无法表示意见 |
| adverse_opinion | 否定意见 |
| no_audit_performed | 未经审计 |
| uncertain_opinion | 不确定意见 |
| unqualified_opinion_with_material_uncertainty | 无保留意见但存在不确定性 |

**4.4. 使用示例**

**4.4.1. 获取一定报告期内某只股票的财务报告审计意见数据**

```python
import panda_data
result = panda_data.get_audit_opinion(
    symbol="000001.SZ",
    start_quarter="2024q1",
    end_quarter="2025q3",
    market="cn",
    fields=[]
)
print(result)
```

```text
date symbol ... opinion quarter
0 20240420 000001.SZ ... no_audit_performed 2024q1
1 20240816 000001.SZ ... no_audit_performed 2024q2
2 20241019 000001.SZ ... no_audit_performed 2024q3
3 20250315 000001.SZ ... unqualified_opinion 2024q4
4 20250315 000001.SZ ... unqualified_opinion 2024q4
5 20250419 000001.SZ ... no_audit_performed 2025q1
```

**4.4.2. 获取一定报告期内全部股票的财务报告审计意见数据并使用fields**

```python
import panda_data
result = panda_data.get_audit_opinion(
    symbol="",
    start_quarter="2025q1",
    end_quarter="2025q2",
    market="cn",
    fields=["symbol", "date", "audit_type", "opinion"]
)
print(result)
```

```text
date symbol audit_type opinion quarter
0 20250422 000020.SZ financial_statements no_audit_performed 2025q1
1 20250428 000012.SZ financial_statements no_audit_performed 2025q1
2 20250429 000004.SZ financial_statements no_audit_performed 2025q1
3 20250429 000061.SZ financial_statements no_audit_performed 2025q1
4 20250422 000055.SZ financial_statements no_audit_performed 2025q1
... ... ... ... ... ...
4581 20250919 601026.SH financial_statements unqualified_opinion 2025q2
4582 20250828 603027.SH financial_statements unqualified_opinion 2025q2
4583 20250828 603052.SH financial_statements unqualified_opinion 2025q2
4584 20250826 605319.SH financial_statements unqualified_opinion 2025q2
4585 20250818 300943.SZ financial_statements unqualified_opinion 2025q1
```

