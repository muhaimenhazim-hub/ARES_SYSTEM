//+------------------------------------------------------------------+
//|                                                 AresBridgeEA.mq5 |
//|                            ARES AI TRADING SYSTEM - BRIDGE V14.4 |
//|  ACTIVE SYMBOLS SYNC, INDEX ALIAS RESOLUTION & EXACT 1:1.5 R:R   |
//+------------------------------------------------------------------+
#property copyright "ARES AI TRADING SYSTEM"
#property version   "14.40"
#property strict

#include <Trade\Trade.mqh>

input string InpServerURL        = "http://141.98.166.81/api/bridge/sync"; // آدرس سرور ARES
input string InpUserIdentifier   = "";    // ایمیل یا شماره موبایل ثبت شده در سایت
input int    InpSyncSeconds      = 2;     // فاصله همگام سازی (ثانیه)
input int    InpSlippagePoints   = 50;    // حداکثر لغزش مجاز (پوینت)
input int    InpMaxOpenPositions = 3;     // سقف قطعی کل معاملات همزمان
input double InpMaxLotCap        = 0.50;  // سقف قطعی حجم هر معامله (لات)

CTrade ExtTrade;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   EventSetTimer(InpSyncSeconds);
   ExtTrade.SetDeviationInPoints(InpSlippagePoints);
   Print("🚀 ARES Bridge V14.4 Initialized (Max Positions: ", InpMaxOpenPositions, ", Max Lot: ", InpMaxLotCap, "). Syncing with: ", InpServerURL);
   SyncAccountWithServer();
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
}

//+------------------------------------------------------------------+
//| Timer function                                                   |
//+------------------------------------------------------------------+
void OnTimer()
{
   SyncAccountWithServer();
}

//+------------------------------------------------------------------+
//| بررسی فعال و قابل معامله بودن یک نماد در بروکر                  |
//+------------------------------------------------------------------+
bool TryActivateSymbol(string sym)
{
   if(sym == "") return false;
   if(!SymbolSelect(sym, true)) return false;

   long tradeMode = SymbolInfoInteger(sym, SYMBOL_TRADE_MODE);
   if(tradeMode == SYMBOL_TRADE_MODE_DISABLED) return false;

   double bid = SymbolInfoDouble(sym, SYMBOL_BID);
   if(bid <= 0.0)
   {
      Sleep(100);
      bid = SymbolInfoDouble(sym, SYMBOL_BID);
   }
   return (bid > 0.0);
}

//+------------------------------------------------------------------+
//| تشخیص هوشمند نام دقیق نماد در بروکر (با پشتیبانی از شاخص‌ها)    |
//+------------------------------------------------------------------+
string ResolveBrokerSymbol(string rawSymbol)
{
   string clean = rawSymbol;
   StringReplace(clean, ".", "");
   StringReplace(clean, " ", "");
   string cleanUpper = clean;
   StringToUpper(cleanUpper);

   // ۱. پشتیبانی ویژه از نام‌های متفاوت شاخص NASDAQ 100 در بروکرها
   if(cleanUpper == "NAS100" || cleanUpper == "NASDAQ100" || cleanUpper == "NASDAQ" ||
      cleanUpper == "USTEC" || cleanUpper == "US100" || cleanUpper == "NDX100" ||
      cleanUpper == "NDX" || cleanUpper == "NQ")
   {
      string nasCandidates[13];
      nasCandidates[0]  = rawSymbol;
      nasCandidates[1]  = "NAS100.";
      nasCandidates[2]  = "NAS100";
      nasCandidates[3]  = "USTEC.";
      nasCandidates[4]  = "USTEC";
      nasCandidates[5]  = "US100.";
      nasCandidates[6]  = "US100";
      nasCandidates[7]  = "NDX100";
      nasCandidates[8]  = "NDX";
      nasCandidates[9]  = "US100Cash";
      nasCandidates[10] = "NAS100_i";
      nasCandidates[11] = "NAS100m";
      nasCandidates[12] = "NASDAQ";

      for(int i = 0; i < 13; i++)
      {
         if(TryActivateSymbol(nasCandidates[i])) return nasCandidates[i];
      }

      int totalNas = SymbolsTotal(false);
      for(int i = 0; i < totalNas; i++)
      {
         string symName = SymbolName(i, false);
         string symUpper = symName;
         StringToUpper(symUpper);
         if(StringFind(symUpper, "NAS100") == 0 || StringFind(symUpper, "USTEC") == 0 ||
            StringFind(symUpper, "US100") == 0 || StringFind(symUpper, "NDX") == 0 ||
            StringFind(symUpper, "NASDAQ") == 0)
         {
            if(TryActivateSymbol(symName)) return symName;
         }
      }
      return rawSymbol;
   }

   // ۲. پشتیبانی ویژه از نام‌های متفاوت شاخص S&P 500 در بروکرها
   if(cleanUpper == "US500" || cleanUpper == "SP500" || cleanUpper == "SPX500" ||
      cleanUpper == "SPX" || cleanUpper == "S&P500" || cleanUpper == "ES")
   {
      string spCandidates[11];
      spCandidates[0]  = rawSymbol;
      spCandidates[1]  = "US500.";
      spCandidates[2]  = "US500";
      spCandidates[3]  = "SP500.";
      spCandidates[4]  = "SP500";
      spCandidates[5]  = "SPX500.";
      spCandidates[6]  = "SPX500";
      spCandidates[7]  = "SPX";
      spCandidates[8]  = "US500Cash";
      spCandidates[9]  = "US500_i";
      spCandidates[10] = "US500m";

      for(int i = 0; i < 11; i++)
      {
         if(TryActivateSymbol(spCandidates[i])) return spCandidates[i];
      }

      int totalSp = SymbolsTotal(false);
      for(int i = 0; i < totalSp; i++)
      {
         string symName = SymbolName(i, false);
         string symUpper = symName;
         StringToUpper(symUpper);
         if(StringFind(symUpper, "US500") == 0 || StringFind(symUpper, "SP500") == 0 ||
            StringFind(symUpper, "SPX500") == 0 || StringFind(symUpper, "SPX") == 0)
         {
            if(TryActivateSymbol(symName)) return symName;
         }
      }
      return rawSymbol;
   }

   // ۳. سایر نمادها (جفت‌ارزها و طلا)
   string candidates[10];
   candidates[0] = rawSymbol;
   candidates[1] = clean + ".";
   candidates[2] = clean;
   candidates[3] = clean + "_i";
   candidates[4] = clean + "m";
   candidates[5] = clean + ".a";
   candidates[6] = clean + ".pro";
   candidates[7] = (cleanUpper == "XAUUSD") ? "GOLD." : rawSymbol;
   candidates[8] = (cleanUpper == "XAUUSD") ? "GOLD"  : rawSymbol;
   candidates[9] = (cleanUpper == "XAUUSD") ? "GOLDm" : rawSymbol;

   for(int i = 0; i < 10; i++)
   {
      if(TryActivateSymbol(candidates[i])) return candidates[i];
   }

   int total = SymbolsTotal(false);
   for(int i = 0; i < total; i++)
   {
      string symName = SymbolName(i, false);
      string symUpper = symName;
      StringToUpper(symUpper);
      if(StringFind(symUpper, cleanUpper) == 0)
      {
         if(TryActivateSymbol(symName)) return symName;
      }
   }
   return rawSymbol;
}

//+------------------------------------------------------------------+
//| ساخت لیست نمادهای واقعی بروکر جهت ارسال به سرور ARES             |
//+------------------------------------------------------------------+
string BuildActiveSymbolsJson()
{
   string json = "[";
   int total = SymbolsTotal(false);
   int added = 0;

   for(int i = 0; i < total && added < 60; i++)
   {
      string symName = SymbolName(i, false);
      string upper = symName;
      StringToUpper(upper);

      bool relevant = (
         StringFind(upper, "EURUSD") >= 0 ||
         StringFind(upper, "XAU") >= 0 ||
         StringFind(upper, "GOLD") >= 0 ||
         StringFind(upper, "NAS") >= 0 ||
         StringFind(upper, "USTEC") >= 0 ||
         StringFind(upper, "US100") >= 0 ||
         StringFind(upper, "NDX") >= 0 ||
         StringFind(upper, "US500") >= 0 ||
         StringFind(upper, "SP500") >= 0 ||
         StringFind(upper, "SPX") >= 0
      );

      if(!relevant) continue;

      StringReplace(symName, "\"", "");
      if(added > 0) json += ",";
      json += "\"" + symName + "\"";
      added++;
   }

   json += "]";
   return json;
}

//+------------------------------------------------------------------+
//| تنظیم خودکار Filling Mode متناسب با بروکر                        |
//+------------------------------------------------------------------+
void SetSymbolFillingMode(string sym)
{
   uint filling = (uint)SymbolInfoInteger(sym, SYMBOL_FILLING_MODE);
   if((filling & SYMBOL_FILLING_FOK) != 0)
      ExtTrade.SetTypeFilling(ORDER_FILLING_FOK);
   else if((filling & SYMBOL_FILLING_IOC) != 0)
      ExtTrade.SetTypeFilling(ORDER_FILLING_IOC);
   else
      ExtTrade.SetTypeFilling(ORDER_FILLING_RETURN);
}

//+------------------------------------------------------------------+
//| محاسبه سود خالص واقعی از تاریخچه کل معاملات بسته شده در بروکر    |
//+------------------------------------------------------------------+
double CalculateRealHistoryPnL(double &initialDepositOut)
{
   initialDepositOut = 0.0;
   double netPnL = 0.0;

   if(!HistorySelect(0, TimeCurrent())) return 0.0;

   int totalDeals = HistoryDealsTotal();
   for(int i = 0; i < totalDeals; i++)
   {
      ulong dealTicket = HistoryDealGetTicket(i);
      if(dealTicket == 0) continue;

      long   dealType = HistoryDealGetInteger(dealTicket, DEAL_TYPE);
      double profit   = HistoryDealGetDouble(dealTicket, DEAL_PROFIT);
      double swap     = HistoryDealGetDouble(dealTicket, DEAL_SWAP);
      double comm     = HistoryDealGetDouble(dealTicket, DEAL_COMMISSION);
      double fee      = HistoryDealGetDouble(dealTicket, DEAL_FEE);

      if(dealType == DEAL_TYPE_BALANCE)
      {
         if(profit > 0) initialDepositOut += profit;
      }
      else if(dealType == DEAL_TYPE_BUY || dealType == DEAL_TYPE_SELL)
      {
         netPnL += (profit + swap + comm + fee);
      }
   }
   return netPnL;
}

//+------------------------------------------------------------------+
//| ساخت آرایه JSON از تمام پوزیشن‌های باز فعلی در متاتریدر         |
//+------------------------------------------------------------------+
string BuildOpenPositionsJson(double &floatingPnLOut)
{
   floatingPnLOut = 0.0;
   string json = "[";
   int total = PositionsTotal();
   bool first = true;

   for(int i = 0; i < total; i++)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;

      string sym       = PositionGetString(POSITION_SYMBOL);
      long   posType   = PositionGetInteger(POSITION_TYPE);
      string sideStr   = (posType == POSITION_TYPE_BUY) ? "BUY" : "SELL";
      double priceOpen = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl        = PositionGetDouble(POSITION_SL);
      double tp        = PositionGetDouble(POSITION_TP);
      double vol       = PositionGetDouble(POSITION_VOLUME);
      double profit    = PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP);
      int    digits    = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);

      floatingPnLOut += profit;

      if(!first) json += ",";
      first = false;

      json += StringFormat(
         "{\"ticket\":%I64u,\"symbol\":\"%s\",\"side\":\"%s\",\"entry_price\":%s,\"sl\":%s,\"tp\":%s,\"volume\":%.2f,\"profit\":%.2f}",
         ticket,
         sym,
         sideStr,
         DoubleToString(priceOpen, digits),
         DoubleToString(sl, digits),
         DoubleToString(tp, digits),
         vol,
         profit
      );
   }
   json += "]";
   return json;
}

//+------------------------------------------------------------------+
//| استخراج مقدار یک فیلد از رشته JSON                               |
//+------------------------------------------------------------------+
string ExtractJsonVal(string obj, string key)
{
   string pattern = "\"" + key + "\":";
   int pos = StringFind(obj, pattern);
   if(pos < 0) return "";

   int start = pos + StringLen(pattern);
   while(start < StringLen(obj) && (StringGetCharacter(obj, start) == ' ' || StringGetCharacter(obj, start) == '"'))
      start++;

   int end = start;
   while(end < StringLen(obj))
   {
      ushort ch = StringGetCharacter(obj, end);
      if(ch == '"' || ch == ',' || ch == '}' || ch == ']') break;
      end++;
   }
   return StringSubstr(obj, start, end - start);
}

//+------------------------------------------------------------------+
//| اجرای دستورات دریافتی از سرور هوش مصنوعی ARES                    |
//+------------------------------------------------------------------+
void ProcessServerOrders(string response)
{
   int ordersPos = StringFind(response, "\"orders\":");
   if(ordersPos < 0) return;

   int arrStart = StringFind(response, "[", ordersPos);
   int arrEnd   = StringFind(response, "]", arrStart);
   if(arrStart < 0 || arrEnd <= arrStart + 1) return;

   string ordersContent = StringSubstr(response, arrStart + 1, arrEnd - arrStart - 1);

   int cur = 0;
   while(cur < StringLen(ordersContent))
   {
      int objStart = StringFind(ordersContent, "{", cur);
      if(objStart < 0) break;
      int objEnd = StringFind(ordersContent, "}", objStart);
      if(objEnd < 0) break;

      string orderObj = StringSubstr(ordersContent, objStart, objEnd - objStart + 1);
      ExecuteSingleOrderJson(orderObj);

      cur = objEnd + 1;
   }
}

//+------------------------------------------------------------------+
//| اجرای یک دستور معاملاتی (BUY / SELL / MODIFY / CLOSE)            |
//+------------------------------------------------------------------+
void ExecuteSingleOrderJson(string orderObj)
{
   string action    = ExtractJsonVal(orderObj, "action");
   string rawSymbol = ExtractJsonVal(orderObj, "symbol");
   double volume    = StringToDouble(ExtractJsonVal(orderObj, "volume"));
   double sl        = StringToDouble(ExtractJsonVal(orderObj, "sl"));
   double tp        = StringToDouble(ExtractJsonVal(orderObj, "tp"));
   double slDist    = StringToDouble(ExtractJsonVal(orderObj, "sl_dist"));
   double tpDist    = StringToDouble(ExtractJsonVal(orderObj, "tp_dist"));
   ulong  ticket    = (ulong)StringToInteger(ExtractJsonVal(orderObj, "ticket"));

   string sym = ResolveBrokerSymbol(rawSymbol);
   SetSymbolFillingMode(sym);
   int    digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
   double point  = SymbolInfoDouble(sym, SYMBOL_POINT);

   if(action == "BUY" || action == "SELL")
   {
      // --- سد دفاعی ۱: بررسی سقف قطعی حداکثر ۳ معامله باز در بروکر ---
      if(PositionsTotal() >= InpMaxOpenPositions)
      {
         Print("🛑 [ARES EA GATE]: رد دستور ", action, " روی ", sym, " — سقف مجاز ", InpMaxOpenPositions, " معامله تکمیل است.");
         return;
      }

      // --- سد دفاعی ۲: عدم باز کردن معامله مجدد روی نماد فعال ---
      int curTotal = PositionsTotal();
      for(int i = 0; i < curTotal; i++)
      {
         ulong posTicket = PositionGetTicket(i);
         if(posTicket > 0)
         {
            if(PositionGetString(POSITION_SYMBOL) == sym)
            {
               Print("🛑 [ARES EA GATE]: رد دستور ", action, " روی ", sym, " — این نماد هم‌اکنون پوزیشن فعال دارد (تیکت #", posTicket, ").");
               return;
            }
         }
      }

      // --- سد دفاعی ۳: اعمال سقف حجم ایمن و نرمال‌سازی دقیق گام حجم ---
      if(volume > InpMaxLotCap)
      {
         Print("⚠️ [ARES EA GATE]: حجم ارسالی (", volume, " لات) از سقف مجاز (", InpMaxLotCap, " لات) بیشتر بود؛ به سقف ایمن کاهش یافت.");
         volume = InpMaxLotCap;
      }

      double minVol = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN);
      double maxVol = SymbolInfoDouble(sym, SYMBOL_VOLUME_MAX);
      double step   = SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP);
      int volDigits = 2;
      if(step > 0.0)
      {
         if(step >= 1.0) volDigits = 0;
         else if(step >= 0.1) volDigits = 1;
         else if(step >= 0.01) volDigits = 2;
         else volDigits = 3;
         volume = MathFloor((volume / step) + 1e-9) * step;
      }
      if(volume < minVol) volume = minVol;
      if(volume > maxVol) volume = maxVol;
      volume = NormalizeDouble(volume, volDigits);

      double ask = SymbolInfoDouble(sym, SYMBOL_ASK);
      double bid = SymbolInfoDouble(sym, SYMBOL_BID);
      double stopsLevel = (double)SymbolInfoInteger(sym, SYMBOL_TRADE_STOPS_LEVEL) * point;
      double spread     = MathMax(0.0, ask - bid);

      double normSL = NormalizeDouble(sl, digits);
      double normTP = NormalizeDouble(tp, digits);

      // --- محاسبه دقیق SL و TP نسبت به قیمت لحظه‌ای واقعی بروکر (تضمین نسبت 1:1.5) ---
      if(slDist > 0.0)
      {
         double minAllowedDist = stopsLevel + spread + (10.0 * point);
         if(slDist < minAllowedDist)
            slDist = minAllowedDist;

         double effectiveTpDist = (tpDist > 0.0) ? MathMax(tpDist, slDist * 1.5) : (slDist * 1.5);

         if(action == "BUY")
         {
            normSL = NormalizeDouble(ask - slDist, digits);
            normTP = NormalizeDouble(ask + effectiveTpDist, digits);
         }
         else
         {
            normSL = NormalizeDouble(bid + slDist, digits);
            normTP = NormalizeDouble(bid - effectiveTpDist, digits);
         }
      }

      bool ok = false;
      if(action == "BUY")
      {
         if(normSL >= ask) normSL = 0;
         if(normTP > 0 && normTP <= ask) normTP = 0;
         ok = ExtTrade.Buy(volume, sym, ask, normSL, normTP, "ARES_AI");
         if(!ok && (normSL > 0 || normTP > 0))
         {
            ok = ExtTrade.Buy(volume, sym, ask, 0, 0, "ARES_AI");
            if(ok)
            {
               Sleep(200);
               for(int p = PositionsTotal() - 1; p >= 0; p--)
               {
                  ulong pt = PositionGetTicket(p);
                  if(pt > 0 && PositionGetString(POSITION_SYMBOL) == sym)
                  {
                     double openP = PositionGetDouble(POSITION_PRICE_OPEN);
                     if(slDist > 0.0)
                     {
                        double effTp = (tpDist > 0.0) ? MathMax(tpDist, slDist * 1.5) : (slDist * 1.5);
                        normSL = NormalizeDouble(openP - slDist, digits);
                        normTP = NormalizeDouble(openP + effTp, digits);
                     }
                     ExtTrade.PositionModify(pt, normSL, normTP);
                     break;
                  }
               }
            }
         }
      }
      else
      {
         if(normSL > 0 && normSL <= bid) normSL = 0;
         if(normTP >= bid) normTP = 0;
         ok = ExtTrade.Sell(volume, sym, bid, normSL, normTP, "ARES_AI");
         if(!ok && (normSL > 0 || normTP > 0))
         {
            ok = ExtTrade.Sell(volume, sym, bid, 0, 0, "ARES_AI");
            if(ok)
            {
               Sleep(200);
               for(int p = PositionsTotal() - 1; p >= 0; p--)
               {
                  ulong pt = PositionGetTicket(p);
                  if(pt > 0 && PositionGetString(POSITION_SYMBOL) == sym)
                  {
                     double openP = PositionGetDouble(POSITION_PRICE_OPEN);
                     if(slDist > 0.0)
                     {
                        double effTp = (tpDist > 0.0) ? MathMax(tpDist, slDist * 1.5) : (slDist * 1.5);
                        normSL = NormalizeDouble(openP + slDist, digits);
                        normTP = NormalizeDouble(openP - effTp, digits);
                     }
                     ExtTrade.PositionModify(pt, normSL, normTP);
                     break;
                  }
               }
            }
         }
      }
      Print("🔥 Order Executed [", action, " ", sym, " (raw:", rawSymbol, ") Vol:", volume, " SL:", DoubleToString(normSL, digits), " TP:", DoubleToString(normTP, digits), "] Result: ", ok, " Retcode: ", ExtTrade.ResultRetcodeDescription());
   }
   else if(action == "CLOSE")
   {
      if(ticket > 0 && PositionSelectByTicket(ticket))
         ExtTrade.PositionClose(ticket);
      else
      {
         for(int i = PositionsTotal() - 1; i >= 0; i--)
         {
            ulong t = PositionGetTicket(i);
            if(PositionGetString(POSITION_SYMBOL) == sym)
               ExtTrade.PositionClose(t);
         }
      }
   }
   else if(action == "MODIFY")
   {
      double normSL = NormalizeDouble(sl, digits);
      double normTP = NormalizeDouble(tp, digits);
      if(ticket > 0 && PositionSelectByTicket(ticket))
         ExtTrade.PositionModify(ticket, normSL, normTP);
      else
      {
         for(int i = PositionsTotal() - 1; i >= 0; i--)
         {
            ulong t = PositionGetTicket(i);
            if(PositionGetString(POSITION_SYMBOL) == sym)
               ExtTrade.PositionModify(t, normSL, normTP);
         }
      }
   }
}

//+------------------------------------------------------------------+
//| ارسال وضعیت زنده حساب، سود واقعی، پوزیشن‌ها و نمادها به سرور    |
//+------------------------------------------------------------------+
void SyncAccountWithServer()
{
   static int lastWebErr = 0;

   long   login   = AccountInfoInteger(ACCOUNT_LOGIN);
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double equity  = AccountInfoDouble(ACCOUNT_EQUITY);
   string company = AccountInfoString(ACCOUNT_COMPANY);
   string server  = AccountInfoString(ACCOUNT_SERVER);

   StringReplace(company, "\"", "");
   StringReplace(server, "\"", "");

   double initialDeposit = 0.0;
   double historyPnL     = CalculateRealHistoryPnL(initialDeposit);
   double floatingPnL    = 0.0;
   string openPosJson    = BuildOpenPositionsJson(floatingPnL);
   string activeSymsJson = BuildActiveSymbolsJson();

   string ident = (InpUserIdentifier != "") ? InpUserIdentifier : IntegerToString(login);

   string payload = StringFormat(
      "{\"identifier\":\"%s\",\"login\":%I64d,\"balance\":%.2f,\"equity\":%.2f,\"history_pnl\":%.2f,\"floating_pnl\":%.2f,\"initial_deposit\":%.2f,\"broker\":\"%s\",\"server\":\"%s\",\"open_positions\":%s,\"active_symbols\":%s}",
      ident, login, balance, equity, historyPnL, floatingPnL, initialDeposit, company, server, openPosJson, activeSymsJson
   );

   char postData[];
   int len = StringToCharArray(payload, postData, 0, WHOLE_ARRAY, CP_UTF8);
   if(len > 0) ArrayResize(postData, len - 1);

   char   resultData[];
   string resultHeaders;
   string headers = "Content-Type: application/json\r\nConnection: keep-alive\r\n";

   ResetLastError();
   int res = WebRequest("POST", InpServerURL, headers, 3000, postData, resultData, resultHeaders);
   if(res == 200)
   {
      lastWebErr = 0;
      string responseStr = CharArrayToString(resultData, 0, WHOLE_ARRAY, CP_UTF8);
      ProcessServerOrders(responseStr);
   }
   else
   {
      int err = GetLastError();
      if(err != lastWebErr)
      {
         lastWebErr = err;
         Print("⚠️ [ARES Sync Error] HTTP=", res, " LastError=", err);
      }
   }
}
//+------------------------------------------------------------------+