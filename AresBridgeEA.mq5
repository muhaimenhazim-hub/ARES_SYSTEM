//+------------------------------------------------------------------+
//|                                                AresBridgeEA.mq5  |
//|                        ARES AI TRADING SYSTEM - BRIDGE V14.2     |
//|          HARD 3-POSITION GATE, ANTI-DUPLICATION & AUTO-SYMBOL    |
//+------------------------------------------------------------------+
#property copyright "ARES AI TRADING SYSTEM"
#property version   "14.20"
#property strict

#include <Trade\Trade.mqh>

input string InpServerURL        = "http://141.98.166.81/api/bridge/sync"; // آدرس سرور ARES
input string InpUserIdentifier   = "";                                      // ایمیل یا شماره موبایل ثبت شده در سایت
input int    InpSyncSeconds      = 2;                                       // فاصله همگام سازی (ثانیه)
input int    InpSlippagePoints   = 50;                                      // حداکثر لغزش مجاز (پوینت)
input int    InpMaxOpenPositions = 3;                                       // سقف قطعی کل معاملات همزمان
input double InpMaxLotCap        = 0.50;                                    // سقف قطعی حجم هر معامله (لات)

CTrade ExtTrade;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   EventSetTimer(InpSyncSeconds);
   ExtTrade.SetDeviationInPoints(InpSlippagePoints);
   Print("🚀 ARES Bridge V14.2 Initialized (Max Positions: ", InpMaxOpenPositions, ", Max Lot: ", InpMaxLotCap, "). Syncing with: ", InpServerURL);
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
//| تشخیص هوشمند نام دقیق نماد در بروکر (با نقطه یا پسوند)            |
//+------------------------------------------------------------------+
string ResolveBrokerSymbol(string rawSymbol)
{
   string clean = rawSymbol;
   StringReplace(clean, ".", "");
   StringReplace(clean, " ", "");
   
   // ۱. بررسی نام مستقیم یا همراه با نقطه (مخصوص آرون مارکتس)
   string candidates[6];
   candidates[0] = rawSymbol;
   candidates[1] = clean + ".";
   candidates[2] = clean;
   candidates[3] = clean + "_i";
   candidates[4] = clean + "m";
   candidates[5] = clean + ".a";
   
   for(int i = 0; i < 6; i++)
   {
      if(SymbolSelect(candidates[i], true))
      {
         double bid = SymbolInfoDouble(candidates[i], SYMBOL_BID);
         if(bid > 0) return candidates[i];
      }
   }
   
   // ۲. جستجو در کل نمادهای بروکر
   int total = SymbolsTotal(false);
   for(int i = 0; i < total; i++)
   {
      string symName = SymbolName(i, false);
      if(StringFind(symName, clean) == 0)
      {
         SymbolSelect(symName, true);
         return symName;
      }
   }
   return rawSymbol;
}

//+------------------------------------------------------------------+
//| تنظیم خودکار Filling Mode متناسب با بروکر آرون مارکتس             |
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
//| محاسبه سود خالص واقعی از تاریخچه کل معاملات بسته شده در بروکر     |
//+------------------------------------------------------------------+
double CalculateRealHistoryPnL(double &initialDepositOut)
{
   initialDepositOut = 0.0;
   double netPnL = 0.0;
   
   if(!HistorySelect(0, TimeCurrent()))
      return 0.0;
      
   int totalDeals = HistoryDealsTotal();
   for(int i = 0; i < totalDeals; i++)
   {
      ulong dealTicket = HistoryDealGetTicket(i);
      if(dealTicket == 0) continue;
      
      long dealType = HistoryDealGetInteger(dealTicket, DEAL_TYPE);
      double profit = HistoryDealGetDouble(dealTicket, DEAL_PROFIT);
      double swap   = HistoryDealGetDouble(dealTicket, DEAL_SWAP);
      double comm   = HistoryDealGetDouble(dealTicket, DEAL_COMMISSION);
      double fee    = HistoryDealGetDouble(dealTicket, DEAL_FEE);
      
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
//| ساخت آرایه JSON از تمام پوزیشن‌های باز فعلی در متاتریدر           |
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
   while(start < StringLen(obj) && (StringGetCharacter(obj, start) == ' ' || StringGetCharacter(obj, start) == '\"'))
      start++;
      
   int end = start;
   while(end < StringLen(obj))
   {
      ushort ch = StringGetCharacter(obj, end);
      if(ch == '\"' || ch == ',' || ch == '}' || ch == ']') break;
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
   ulong  ticket    = (ulong)StringToInteger(ExtractJsonVal(orderObj, "ticket"));
   
   string sym = ResolveBrokerSymbol(rawSymbol);
   SetSymbolFillingMode(sym);
   int digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
   
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

      // --- سد دفاعی ۳: اعمال سقف حجم ایمن هر معامله ---
      if(volume > InpMaxLotCap)
      {
         Print("⚠️ [ARES EA GATE]: حجم ارسالی (", volume, " لات) از سقف مجاز (", InpMaxLotCap, " لات) بیشتر بود؛ به سقف ایمن کاهش یافت.");
         volume = InpMaxLotCap;
      }

      double minVol = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN);
      double maxVol = SymbolInfoDouble(sym, SYMBOL_VOLUME_MAX);
      double step   = SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP);
      if(step > 0) volume = MathFloor(volume / step) * step;
      if(volume < minVol) volume = minVol;
      if(volume > maxVol) volume = maxVol;
      
      double ask = SymbolInfoDouble(sym, SYMBOL_ASK);
      double bid = SymbolInfoDouble(sym, SYMBOL_BID);
      double normSL = NormalizeDouble(sl, digits);
      double normTP = NormalizeDouble(tp, digits);
      
      bool ok = false;
      if(action == "BUY")
      {
         if(normSL >= ask) normSL = 0;
         if(normTP > 0 && normTP <= ask) normTP = 0;
         ok = ExtTrade.Buy(volume, sym, ask, normSL, normTP, "ARES_AI");
         if(!ok && normSL > 0) ok = ExtTrade.Buy(volume, sym, ask, 0, 0, "ARES_AI");
      }
      else
      {
         if(normSL > 0 && normSL <= bid) normSL = 0;
         if(normTP >= bid) normTP = 0;
         ok = ExtTrade.Sell(volume, sym, bid, normSL, normTP, "ARES_AI");
         if(!ok && normSL > 0) ok = ExtTrade.Sell(volume, sym, bid, 0, 0, "ARES_AI");
      }
      Print("🔥 Order Executed [", action, " ", sym, " Vol:", volume, "] Result: ", ok, " Retcode: ", ExtTrade.ResultRetcodeDescription());
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
//| ارسال وضعیت زنده حساب، سود واقعی و پوزیشن‌ها به سرور             |
//+------------------------------------------------------------------+
void SyncAccountWithServer()
{
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
   
   string ident = (InpUserIdentifier != "") ? InpUserIdentifier : IntegerToString(login);
   
   string payload = StringFormat(
      "{\"identifier\":\"%s\",\"login\":%I64d,\"balance\":%.2f,\"equity\":%.2f,\"history_pnl\":%.2f,\"floating_pnl\":%.2f,\"initial_deposit\":%.2f,\"broker\":\"%s\",\"server\":\"%s\",\"open_positions\":%s}",
      ident, login, balance, equity, historyPnL, floatingPnL, initialDeposit, company, server, openPosJson
   );
   
   char postData[];
   int len = StringToCharArray(payload, postData, 0, WHOLE_ARRAY, CP_UTF8);
   if(len > 0) ArrayResize(postData, len - 1);
   
   char resultData[];
   string resultHeaders;
   string headers = "Content-Type: application/json\r\nConnection: keep-alive\r\n";
   
   ResetLastError();
   int res = WebRequest("POST", InpServerURL, headers, 3000, postData, resultData, resultHeaders);
   if(res == 200)
   {
      string responseStr = CharArrayToString(resultData, 0, WHOLE_ARRAY, CP_UTF8);
      ProcessServerOrders(responseStr);
   }
}
//+------------------------------------------------------------------+