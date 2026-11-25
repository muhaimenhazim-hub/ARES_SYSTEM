//+------------------------------------------------------------------+
//|                                                 AresBridgeEA.mq5 |
//|                            ARES AI TRADING SYSTEM - BRIDGE V15.2 |
//|  1.0R 30%+BE(SPREAD/COMM/SWAP), 1.5R 30%+0.5R, 2.0R 40% & ACK EA |
//+------------------------------------------------------------------+
#property copyright "ARES AI TRADING SYSTEM"
#property version   "15.20"
#property strict

#include <Trade\Trade.mqh>

input string InpServerURL        = "http://141.98.166.81/api/bridge/sync"; // آدرس سرور ARES
input string InpUserIdentifier   = "";    // ایمیل یا شماره موبایل ثبت شده در سایت
input int    InpSyncSeconds      = 2;     // فاصله همگام سازی (ثانیه)
input int    InpSlippagePoints   = 50;    // حداکثر لغزش مجاز (پوینت)
input int    InpMaxOpenPositions = 3;     // سقف قطعی کل معاملات همزمان
input double InpMaxLotCap        = 10.0;  // سقف ایمنی حجم هر معامله (لات)

CTrade ExtTrade;

string   g_procCmdIds[32];
datetime g_procCmdTimes[32];
int      g_procCmdHead = 0;

//+------------------------------------------------------------------+
//| جلوگیری از اجرای تکراری دستور و ساخت لیست تاییدیه تحویل (ACK)   |
//+------------------------------------------------------------------+
bool IsCmdAlreadyProcessed(string cmdId)
{
   if(StringLen(cmdId) == 0) return false;
   for(int i = 0; i < 32; i++)
   {
      if(StringLen(g_procCmdIds[i]) > 0 && g_procCmdIds[i] == cmdId)
         return true;
   }
   return false;
}

void MarkCmdProcessed(string cmdId)
{
   if(StringLen(cmdId) == 0) return;
   if(IsCmdAlreadyProcessed(cmdId)) return;
   g_procCmdIds[g_procCmdHead] = cmdId;
   g_procCmdTimes[g_procCmdHead] = TimeLocal();
   g_procCmdHead = (g_procCmdHead + 1) % 32;
}

string BuildAckedCmdsJson()
{
   datetime now = TimeLocal();
   string json = "[";
   int added = 0;
   for(int i = 0; i < 32; i++)
   {
      if(StringLen(g_procCmdIds[i]) > 0 && (now - g_procCmdTimes[i]) <= 120)
      {
         if(added > 0) json += ",";
         json += "\"" + SanitizeJsonStr(g_procCmdIds[i]) + "\"";
         added++;
      }
   }
   json += "]";
   return json;
}

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   ArrayInitialize(g_procCmdTimes, 0);
   EventSetTimer(InpSyncSeconds);
   ExtTrade.SetDeviationInPoints(InpSlippagePoints);
   Print("🚀 ARES Bridge V15.2 Initialized (1.0R 30%+BE, 1.5R 30%+0.5R, 2.0R 40%, ACK+Dedup ON).");
   ManagePositionsAndStagedExits();
   SyncAccountWithServer();
   ExportLiveCandlesFile();
   ExportLiveCalendarFile();
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
   ManagePositionsAndStagedExits();
   SyncAccountWithServer();
   ExportLiveCandlesFile();
   ExportLiveCalendarFile();
}

//+------------------------------------------------------------------+
//| محاسبه امن حجم خروج پله‌ای با رعایت حداقل حجم بروکر (0.01)      |
//+------------------------------------------------------------------+
double CalcSafePartialCloseVolume(string sym, double initVol, double curVol, double targetCumRatio)
{
   double minVol = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN);
   double step   = SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP);
   if(minVol <= 0.0) minVol = 0.01;
   if(step <= 0.0)   step   = 0.01;

   int volDigits = 2;
   if(step >= 1.0) volDigits = 0;
   else if(step >= 0.1) volDigits = 1;
   else if(step >= 0.01) volDigits = 2;
   else volDigits = 3;

   if(curVol <= (minVol + 1e-9))
      return 0.0;

   double desiredRemaining = initVol * MathMax(0.0, 1.0 - targetCumRatio);
   double rawClose = curVol - desiredRemaining;
   if(rawClose <= 0.0)
      return 0.0;

   double closeVol = MathFloor((rawClose / step) + 1e-9) * step;
   closeVol = NormalizeDouble(closeVol, volDigits);
   if(closeVol < minVol)
      return 0.0;

   double remAfter = NormalizeDouble(curVol - closeVol, volDigits);
   if(remAfter < (minVol - 1e-9))
   {
      double maxSafe = MathFloor(((curVol - minVol) / step) + 1e-9) * step;
      maxSafe = NormalizeDouble(maxSafe, volDigits);
      if(maxSafe < minVol)
         return 0.0;
      closeVol = maxSafe;
   }
   return closeVol;
}

//+------------------------------------------------------------------+
//| محاسبه دقیق نقطه سر به سر با احتساب اسپرد، کمیسیون و سواپ بروکر |
//+------------------------------------------------------------------+
double CalcBrokerBreakEvenSL(
   ulong ticket, string sym, long posType, double priceOpen,
   double riskDist, double remVol, int digits, double point,
   double ask, double bid
)
{
   double spreadPrice = MathMax(0.0, ask - bid);
   double spreadBuf   = MathMax(2.0 * point, spreadPrice);

   double curSwap   = PositionGetDouble(POSITION_SWAP);
   long   posId     = PositionGetInteger(POSITION_IDENTIFIER);
   double entryComm = 0.0;
   double entryVol  = 0.0;

   if(posId > 0 && HistorySelectByPosition(posId))
   {
      int deals = HistoryDealsTotal();
      for(int d = 0; d < deals; d++)
      {
         ulong dt = HistoryDealGetTicket(d);
         if(dt == 0) continue;
         long dEntry = HistoryDealGetInteger(dt, DEAL_ENTRY);
         if(dEntry == DEAL_ENTRY_IN)
         {
            entryComm += HistoryDealGetDouble(dt, DEAL_COMMISSION) + HistoryDealGetDouble(dt, DEAL_FEE);
            entryVol  += HistoryDealGetDouble(dt, DEAL_VOLUME);
         }
      }
   }

   double estExitComm = (entryVol > 0.0) ? (entryComm * (remVol / entryVol)) : entryComm;
   double netCostUsd  = MathMax(0.0, -(entryComm + estExitComm + curSwap));

   double costOffset = 0.0;
   if(netCostUsd > 0.0 && remVol > 0.0)
   {
      ENUM_ORDER_TYPE oType = (posType == POSITION_TYPE_BUY) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
      double testStep       = MathMax(100.0 * point, riskDist * 0.1);
      double testTarget     = (posType == POSITION_TYPE_BUY) ? (priceOpen + testStep) : (priceOpen - testStep);
      double profitTest     = 0.0;
      if(OrderCalcProfit(oType, sym, remVol, priceOpen, testTarget, profitTest) && MathAbs(profitTest) > 0.0)
      {
         double usdPerPrice = MathAbs(profitTest) / testStep;
         if(usdPerPrice > 0.0)
            costOffset = netCostUsd / usdPerPrice;
      }
   }

   double totalOffset = costOffset + spreadBuf;
   double maxSafeOff  = riskDist * 0.40;
   if(totalOffset > maxSafeOff) totalOffset = maxSafeOff;
   if(totalOffset < point)      totalOffset = point;

   if(posType == POSITION_TYPE_BUY)
      return NormalizeDouble(priceOpen + totalOffset, digits);
   return NormalizeDouble(priceOpen - totalOffset, digits);
}

//+------------------------------------------------------------------+
//| مدیریت خروج پله‌ای 1.0R (30% + ریسک‌فری) و 1.5R (30% + 0.5R)    |
//+------------------------------------------------------------------+
void ManagePositionsAndStagedExits()
{
   int total = PositionsTotal();
   for(int i = total - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;

      string sym       = PositionGetString(POSITION_SYMBOL);
      long   posType   = PositionGetInteger(POSITION_TYPE);
      double priceOpen = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl        = PositionGetDouble(POSITION_SL);
      double tp        = PositionGetDouble(POSITION_TP);
      double curVol    = PositionGetDouble(POSITION_VOLUME);
      if(priceOpen <= 0.0 || curVol <= 0.0) continue;

      int    digits     = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
      double point      = SymbolInfoDouble(sym, SYMBOL_POINT);
      double ask        = SymbolInfoDouble(sym, SYMBOL_ASK);
      double bid        = SymbolInfoDouble(sym, SYMBOL_BID);
      double stopsLevel = (double)SymbolInfoInteger(sym, SYMBOL_TRADE_STOPS_LEVEL) * point;
      if(ask <= 0.0 || bid <= 0.0 || point <= 0.0) continue;

      string gvInitVol  = "ARES_IV_" + IntegerToString((long)ticket);
      string gvRiskDist = "ARES_RD_" + IntegerToString((long)ticket);
      string gvStage    = "ARES_ST_" + IntegerToString((long)ticket);

      double initVol = GlobalVariableCheck(gvInitVol) ? GlobalVariableGet(gvInitVol) : curVol;
      if(initVol < curVol) initVol = curVol;
      if(!GlobalVariableCheck(gvInitVol)) GlobalVariableSet(gvInitVol, initVol);

      double riskDist = GlobalVariableCheck(gvRiskDist) ? GlobalVariableGet(gvRiskDist) : 0.0;
      if(riskDist <= (5.0 * point))
      {
         if(tp > 0.0 && MathAbs(tp - priceOpen) > (10.0 * point))
            riskDist = MathAbs(tp - priceOpen) / 2.0;
         else if(sl > 0.0)
            riskDist = MathAbs(priceOpen - sl);

         if(riskDist > (5.0 * point))
            GlobalVariableSet(gvRiskDist, riskDist);
      }
      if(riskDist <= (5.0 * point)) continue;

      int stage = GlobalVariableCheck(gvStage) ? (int)GlobalVariableGet(gvStage) : 0;
      if(stage == 0)
      {
         if((posType == POSITION_TYPE_BUY && sl >= priceOpen) ||
            (posType == POSITION_TYPE_SELL && sl > 0.0 && sl <= priceOpen))
            stage = 1;
      }
      if(stage < 2 && initVol > 0.0 && curVol <= (initVol * 0.45 + 1e-9))
         stage = 2;

      if(posType == POSITION_TYPE_BUY)
      {
         // مرحله ۱: رسیدن به ریوارد 1.0R -> بستن 30% حجم اولیه + انتقال SL به نقطه ورود (اسپرد + کمیسیون + سواپ)
         if(stage < 1 && bid >= (priceOpen + riskDist))
         {
            double closeVol1 = CalcSafePartialCloseVolume(sym, initVol, curVol, 0.30);
            if(closeVol1 > 0.0)
            {
               SetSymbolFillingMode(sym);
               if(ExtTrade.PositionClosePartial(ticket, closeVol1))
               {
                  Print("💰 [ARES TP1 1.0R]: BUY #", ticket, " (", sym, ") closed 30% partial: ", DoubleToString(closeVol1, 2));
                  if(PositionSelectByTicket(ticket))
                     curVol = PositionGetDouble(POSITION_VOLUME);
                  else
                     curVol = MathMax(0.0, curVol - closeVol1);
               }
            }
            else
            {
               Print("ℹ️ [ARES TP1 1.0R]: BUY #", ticket, " (", sym, ") min-lot 0.01 protected at BE.");
            }

            if(PositionSelectByTicket(ticket))
            {
               double curSL = PositionGetDouble(POSITION_SL);
               double curTP = PositionGetDouble(POSITION_TP);
               double beSL  = CalcBrokerBreakEvenSL(ticket, sym, posType, priceOpen, riskDist, curVol, digits, point, ask, bid);
               double maxAllowedSL = NormalizeDouble(bid - stopsLevel - (2.0 * point), digits);
               if(beSL > maxAllowedSL) beSL = maxAllowedSL;

               if(curSL < priceOpen && beSL > curSL && beSL >= priceOpen)
               {
                  SetSymbolFillingMode(sym);
                  if(ExtTrade.PositionModify(ticket, beSL, curTP))
                     Print("🛡️ [ARES 1.0R RISK-FREE]: BUY #", ticket, " (", sym, ") -> SL moved to Break-Even (Spread+Comm+Swap): ", DoubleToString(beSL, digits));
               }
            }
            stage = 1;
            GlobalVariableSet(gvStage, 1.0);
         }

         // مرحله ۲: رسیدن به ریوارد 1.5R (TP2) -> بستن 30% حجم اولیه + انتقال SL به 0.5R
         if(stage < 2 && bid >= (priceOpen + (riskDist * 1.5)))
         {
            double closeVol2 = CalcSafePartialCloseVolume(sym, initVol, curVol, 0.60);
            bool partialOk = true;
            if(closeVol2 > 0.0)
            {
               SetSymbolFillingMode(sym);
               partialOk = ExtTrade.PositionClosePartial(ticket, closeVol2);
               if(partialOk)
                  Print("💰 [ARES TP2 1.5R]: BUY #", ticket, " (", sym, ") closed 30% partial: ", DoubleToString(closeVol2, 2));
            }

            if((partialOk || closeVol2 <= 0.0) && PositionSelectByTicket(ticket))
            {
               double curSL = PositionGetDouble(POSITION_SL);
               double curTP = PositionGetDouble(POSITION_TP);
               double trailSL = NormalizeDouble(priceOpen + (riskDist * 0.50), digits);
               double maxAllowedSL = NormalizeDouble(bid - stopsLevel - (2.0 * point), digits);
               if(trailSL > maxAllowedSL) trailSL = maxAllowedSL;
               if(trailSL > curSL)
               {
                  SetSymbolFillingMode(sym);
                  if(ExtTrade.PositionModify(ticket, trailSL, curTP))
                     Print("🔒 [ARES 1.5R TRAIL 0.5R]: BUY #", ticket, " (", sym, ") -> SL moved to 0.5R: ", DoubleToString(trailSL, digits));
               }
               stage = 2;
               GlobalVariableSet(gvStage, 2.0);
            }
         }
      }
      else if(posType == POSITION_TYPE_SELL)
      {
         // مرحله ۱: رسیدن به ریوارد 1.0R -> بستن 30% حجم اولیه + انتقال SL به نقطه ورود (اسپرد + کمیسیون + سواپ)
         if(stage < 1 && ask <= (priceOpen - riskDist))
         {
            double closeVol1 = CalcSafePartialCloseVolume(sym, initVol, curVol, 0.30);
            if(closeVol1 > 0.0)
            {
               SetSymbolFillingMode(sym);
               if(ExtTrade.PositionClosePartial(ticket, closeVol1))
               {
                  Print("💰 [ARES TP1 1.0R]: SELL #", ticket, " (", sym, ") closed 30% partial: ", DoubleToString(closeVol1, 2));
                  if(PositionSelectByTicket(ticket))
                     curVol = PositionGetDouble(POSITION_VOLUME);
                  else
                     curVol = MathMax(0.0, curVol - closeVol1);
               }
            }
            else
            {
               Print("ℹ️ [ARES TP1 1.0R]: SELL #", ticket, " (", sym, ") min-lot 0.01 protected at BE.");
            }

            if(PositionSelectByTicket(ticket))
            {
               double curSL = PositionGetDouble(POSITION_SL);
               double curTP = PositionGetDouble(POSITION_TP);
               double beSL  = CalcBrokerBreakEvenSL(ticket, sym, posType, priceOpen, riskDist, curVol, digits, point, ask, bid);
               double minAllowedSL = NormalizeDouble(ask + stopsLevel + (2.0 * point), digits);
               if(beSL < minAllowedSL) beSL = minAllowedSL;

               if((curSL == 0.0 || curSL > priceOpen) && (curSL == 0.0 || beSL < curSL) && beSL <= priceOpen)
               {
                  SetSymbolFillingMode(sym);
                  if(ExtTrade.PositionModify(ticket, beSL, curTP))
                     Print("🛡️ [ARES 1.0R RISK-FREE]: SELL #", ticket, " (", sym, ") -> SL moved to Break-Even (Spread+Comm+Swap): ", DoubleToString(beSL, digits));
               }
            }
            stage = 1;
            GlobalVariableSet(gvStage, 1.0);
         }

         // مرحله ۲: رسیدن به ریوارد 1.5R (TP2) -> بستن 30% حجم اولیه + انتقال SL به 0.5R
         if(stage < 2 && ask <= (priceOpen - (riskDist * 1.5)))
         {
            double closeVol2 = CalcSafePartialCloseVolume(sym, initVol, curVol, 0.60);
            bool partialOk = true;
            if(closeVol2 > 0.0)
            {
               SetSymbolFillingMode(sym);
               partialOk = ExtTrade.PositionClosePartial(ticket, closeVol2);
               if(partialOk)
                  Print("💰 [ARES TP2 1.5R]: SELL #", ticket, " (", sym, ") closed 30% partial: ", DoubleToString(closeVol2, 2));
            }

            if((partialOk || closeVol2 <= 0.0) && PositionSelectByTicket(ticket))
            {
               double curSL = PositionGetDouble(POSITION_SL);
               double curTP = PositionGetDouble(POSITION_TP);
               double trailSL = NormalizeDouble(priceOpen - (riskDist * 0.50), digits);
               double minAllowedSL = NormalizeDouble(ask + stopsLevel + (2.0 * point), digits);
               if(trailSL < minAllowedSL) trailSL = minAllowedSL;
               if(curSL == 0.0 || trailSL < curSL)
               {
                  SetSymbolFillingMode(sym);
                  if(ExtTrade.PositionModify(ticket, trailSL, curTP))
                     Print("🔒 [ARES 1.5R TRAIL 0.5R]: SELL #", ticket, " (", sym, ") -> SL moved to 0.5R: ", DoubleToString(trailSL, digits));
               }
               stage = 2;
               GlobalVariableSet(gvStage, 2.0);
            }
         }
      }
   }
}

//+------------------------------------------------------------------+
//| بررسی فعال و قابل معامله بودن یک نماد در بروکر                  |
//+------------------------------------------------------------------+
bool TryActivateSymbol(string sym)
{
   if(sym == "") return false;
   if(!SymbolSelect(sym, true)) return false;

   long tradeMode = SymbolInfoInteger(sym, SYMBOL_TRADE_MODE);
   if(tradeMode == SYMBOL_TRADE_MODE_DISABLED || tradeMode == SYMBOL_TRADE_MODE_CLOSEONLY) return false;

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
      cleanUpper == "NDXUSD" || cleanUpper == "NDX" || cleanUpper == "NQ")
   {
      string nasCandidates[15];
      nasCandidates[0]  = rawSymbol;
      nasCandidates[1]  = "NAS100.";
      nasCandidates[2]  = "NAS100";
      nasCandidates[3]  = "USTEC.";
      nasCandidates[4]  = "USTEC";
      nasCandidates[5]  = "US100.";
      nasCandidates[6]  = "US100";
      nasCandidates[7]  = "NDXUSD.";
      nasCandidates[8]  = "NDXUSD";
      nasCandidates[9]  = "NDX100";
      nasCandidates[10] = "NDX";
      nasCandidates[11] = "US100Cash";
      nasCandidates[12] = "NAS100_i";
      nasCandidates[13] = "NAS100m";
      nasCandidates[14] = "NASDAQ";

      for(int i = 0; i < 15; i++)
      {
         if(TryActivateSymbol(nasCandidates[i])) return nasCandidates[i];
      }

      int totalNas = SymbolsTotal(false);
      for(int i = 0; i < totalNas; i++)
      {
         string symName = SymbolName(i, false);
         string symUpper = symName;
         StringToUpper(symUpper);
         bool isNdxMatch = (symUpper == "NDX" || StringFind(symUpper, "NDX.") == 0 ||
                            StringFind(symUpper, "NDX_") == 0 || StringFind(symUpper, "NDX100") == 0 ||
                            StringFind(symUpper, "NDXUSD") == 0);
         if(StringFind(symUpper, "NAS100") == 0 || StringFind(symUpper, "USTEC") == 0 ||
            StringFind(symUpper, "US100") == 0 || isNdxMatch ||
            StringFind(symUpper, "NASDAQ") == 0)
         {
            if(TryActivateSymbol(symName)) return symName;
         }
      }
      return rawSymbol;
   }

   // ۲. پشتیبانی ویژه از نام‌های متفاوت شاخص S&P 500 در بروکرها
   if(cleanUpper == "US500" || cleanUpper == "SP500" || cleanUpper == "SPX500" ||
      cleanUpper == "SPXUSD" || cleanUpper == "SPX" || cleanUpper == "S&P500" || cleanUpper == "ES")
   {
      string spCandidates[13];
      spCandidates[0]  = rawSymbol;
      spCandidates[1]  = "US500.";
      spCandidates[2]  = "US500";
      spCandidates[3]  = "SP500.";
      spCandidates[4]  = "SP500";
      spCandidates[5]  = "SPX500.";
      spCandidates[6]  = "SPX500";
      spCandidates[7]  = "SPXUSD.";
      spCandidates[8]  = "SPXUSD";
      spCandidates[9]  = "SPX";
      spCandidates[10] = "US500Cash";
      spCandidates[11] = "US500_i";
      spCandidates[12] = "US500m";

      for(int i = 0; i < 13; i++)
      {
         if(TryActivateSymbol(spCandidates[i])) return spCandidates[i];
      }

      int totalSp = SymbolsTotal(false);
      for(int i = 0; i < totalSp; i++)
      {
         string symName = SymbolName(i, false);
         string symUpper = symName;
         StringToUpper(symUpper);
         bool isSpxMatch = (symUpper == "SPX" || StringFind(symUpper, "SPX.") == 0 ||
                            StringFind(symUpper, "SPX_") == 0 || StringFind(symUpper, "SPX500") == 0 ||
                            StringFind(symUpper, "SPXUSD") == 0);
         if(StringFind(symUpper, "US500") == 0 || StringFind(symUpper, "SP500") == 0 ||
            StringFind(symUpper, "SPX500") == 0 || isSpxMatch)
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
//| ساخت لیست نمادهای واقعاً قابل معامله بروکر جهت ارسال به سرور     |
//+------------------------------------------------------------------+
string BuildActiveSymbolsJson()
{
   static string cachedJson = "[]";
   static datetime lastScanTime = 0;
   datetime now = TimeLocal();
   if(lastScanTime != 0 && (now - lastScanTime) < 60 && cachedJson != "[]")
      return cachedJson;

   string json = "[";
   int total = SymbolsTotal(false);
   int added = 0;

   for(int i = 0; i < total && added < 40; i++)
   {
      string symName = SymbolName(i, false);
      if(StringLen(symName) > 14) continue;

      string upper = symName;
      StringToUpper(upper);

      bool isGoldAlias = (upper == "GOLD" || upper == "GOLD." || upper == "GOLDM" || StringFind(upper, "GOLD.") == 0 || StringFind(upper, "GOLD_") == 0);
      bool isNdxAlias  = (upper == "NDX" || StringFind(upper, "NDX.") == 0 || StringFind(upper, "NDX_") == 0 || StringFind(upper, "NDX100") == 0 || StringFind(upper, "NDXUSD") == 0);
      bool isSpxAlias  = (upper == "SPX" || StringFind(upper, "SPX.") == 0 || StringFind(upper, "SPX_") == 0 || StringFind(upper, "SPX500") == 0 || StringFind(upper, "SPXUSD") == 0);

      bool relevant = (
         StringFind(upper, "EURUSD") == 0 ||
         StringFind(upper, "XAUUSD") == 0 ||
         isGoldAlias ||
         StringFind(upper, "NAS100") == 0 ||
         StringFind(upper, "USTEC") == 0 ||
         StringFind(upper, "US100") == 0 ||
         isNdxAlias ||
         StringFind(upper, "US500") == 0 ||
         StringFind(upper, "SP500") == 0 ||
         isSpxAlias
      );

      if(!relevant) continue;
      if(!SymbolSelect(symName, true)) continue;
      if(SymbolInfoInteger(symName, SYMBOL_TRADE_MODE) != SYMBOL_TRADE_MODE_FULL) continue;
      if(SymbolInfoDouble(symName, SYMBOL_BID) <= 0.0) continue;

      StringReplace(symName, "\"", "");
      if(added > 0) json += ",";
      json += "\"" + symName + "\"";
      added++;
   }

   json += "]";
   cachedJson = json;
   lastScanTime = now;
   return cachedJson;
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
//| پاکسازی رشته برای قرارگیری امن در JSON                           |
//+------------------------------------------------------------------+
string SanitizeJsonStr(string s)
{
   StringReplace(s, "\\", "");
   StringReplace(s, "\"", "");
   StringReplace(s, "\r", " ");
   StringReplace(s, "\n", " ");
   return s;
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

      string sym       = SanitizeJsonStr(PositionGetString(POSITION_SYMBOL));
      string comment   = SanitizeJsonStr(PositionGetString(POSITION_COMMENT));
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
         "{\"ticket\":%I64u,\"symbol\":\"%s\",\"side\":\"%s\",\"entry_price\":%s,\"sl\":%s,\"tp\":%s,\"volume\":%.2f,\"profit\":%.2f,\"comment\":\"%s\"}",
         ticket,
         sym,
         sideStr,
         DoubleToString(priceOpen, digits),
         DoubleToString(sl, digits),
         DoubleToString(tp, digits),
         vol,
         profit,
         comment
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
   string cmdId        = ExtractJsonVal(orderObj, "cmd_id");
   if(StringLen(cmdId) > 0 && IsCmdAlreadyProcessed(cmdId))
   {
      Print("ℹ️ [ARES DEDUP]: دستور تکراری نادیده گرفته شد: ", cmdId);
      return;
   }
   MarkCmdProcessed(cmdId);

   string action       = ExtractJsonVal(orderObj, "action");
   string rawSymbol    = ExtractJsonVal(orderObj, "symbol");
   double volume       = StringToDouble(ExtractJsonVal(orderObj, "volume"));
   double sl           = StringToDouble(ExtractJsonVal(orderObj, "sl"));
   double tp           = StringToDouble(ExtractJsonVal(orderObj, "tp"));
   double slDist       = StringToDouble(ExtractJsonVal(orderObj, "sl_dist"));
   double tpDist       = StringToDouble(ExtractJsonVal(orderObj, "tp_dist"));
   double riskUsd      = StringToDouble(ExtractJsonVal(orderObj, "risk_usd"));
   ulong  ticket       = (ulong)StringToInteger(ExtractJsonVal(orderObj, "ticket"));
   string orderComment = SanitizeJsonStr(ExtractJsonVal(orderObj, "comment"));
   if(orderComment == "") orderComment = "ARES_AI";
   if(StringLen(orderComment) > 31) orderComment = StringSubstr(orderComment, 0, 31);

   string sym = ResolveBrokerSymbol(rawSymbol);
   SetSymbolFillingMode(sym);
   int    digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
   double point  = SymbolInfoDouble(sym, SYMBOL_POINT);

   if(action == "BUY" || action == "SELL")
   {
      // --- سد دفاعی ۰: بررسی فعال بودن معامله نماد در بروکر ---
      bool symReady = TryActivateSymbol(sym);
      long tradeMode = SymbolInfoInteger(sym, SYMBOL_TRADE_MODE);
      if(!symReady || tradeMode == SYMBOL_TRADE_MODE_DISABLED || tradeMode == SYMBOL_TRADE_MODE_CLOSEONLY ||
         (action == "BUY" && tradeMode == SYMBOL_TRADE_MODE_SHORTONLY) ||
         (action == "SELL" && tradeMode == SYMBOL_TRADE_MODE_LONGONLY))
      {
         Print("🛑 [ARES EA GATE]: نماد ", sym, " (raw:", rawSymbol, ") در این بروکر غیرفعال است (TradeMode=", tradeMode, ")؛ سفارش لغو شد.");
         return;
      }

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

      double ask = SymbolInfoDouble(sym, SYMBOL_ASK);
      double bid = SymbolInfoDouble(sym, SYMBOL_BID);
      ENUM_ORDER_TYPE oType = (action == "BUY") ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
      double refPrice       = (action == "BUY") ? ask : bid;
      double stopsLevel     = (double)SymbolInfoInteger(sym, SYMBOL_TRADE_STOPS_LEVEL) * point;
      double spread         = MathMax(0.0, ask - bid);

      if(slDist > 0.0)
      {
         double minAllowedDist = stopsLevel + spread + (10.0 * point);
         if(slDist < minAllowedDist)
            slDist = minAllowedDist;
      }

      double testSL = (action == "BUY") ? (refPrice - slDist) : (refPrice + slDist);

      // --- محاسبه دقیق حجم متناسب با ریسک دلاری واقعی با OrderCalcProfit (موتور رسمی بروکر) ---
      if(riskUsd > 0.0 && slDist > 0.0 && refPrice > 0.0)
      {
         double lossPerLot = 0.0;
         double profit1Lot = 0.0;

         if(OrderCalcProfit(oType, sym, 1.0, refPrice, testSL, profit1Lot) && MathAbs(profit1Lot) > 0.0)
         {
            lossPerLot = MathAbs(profit1Lot);
         }
         else
         {
            double tickSize = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE);
            double tickVal  = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE);
            if(tickSize > 0.0 && tickVal > 0.0)
               lossPerLot = (slDist / tickSize) * tickVal;
         }

         if(lossPerLot > 0.0)
         {
            double calcVol = riskUsd / lossPerLot;
            if(volume > 0.0 && calcVol > (volume * 2.5))
            {
               Print("⚠️ [ARES SIZING GUARD]: calcVol=", DoubleToString(calcVol, 4),
                     " clamped near server volume=", DoubleToString(volume, 4));
               calcVol = volume * 1.5;
            }
            Print("📐 [ARES RISK SIZING]: ", sym, " RiskUSD=$", DoubleToString(riskUsd, 2),
                  " LossPerLot=$", DoubleToString(lossPerLot, 2), " -> CalcVol=", DoubleToString(calcVol, 4));
            volume = calcVol;
         }
      }

      // --- سد دفاعی ۳: کنترل مارجین آزاد، سقف لات و نرمال‌سازی دقیق گام حجم ---
      double freeMargin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
      double margin1Lot = 0.0;
      if(freeMargin > 0.0 && refPrice > 0.0 && OrderCalcMargin(oType, sym, 1.0, refPrice, margin1Lot) && margin1Lot > 0.0)
      {
         double maxMarginVol = (freeMargin * 0.45) / margin1Lot;
         if(volume > maxMarginVol)
            volume = maxMarginVol;
      }

      string symUpper = sym;
      StringToUpper(symUpper);
      bool isGoldSym = (StringFind(symUpper, "XAU") >= 0 || StringFind(symUpper, "GOLD") >= 0);
      double defaultLotCap = isGoldSym ? 5.0 : 10.0;
      double lotCap = (InpMaxLotCap > 0.0) ? MathMin(InpMaxLotCap, defaultLotCap) : defaultLotCap;
      if(volume > lotCap)
      {
         Print("⚠️ [ARES EA GATE]: حجم (", volume, " لات) به سقف ایمن (", lotCap, " لات) محدود شد.");
         volume = lotCap;
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

      // --- کنترل نهایی قطعی: تایید با OrderCalcProfit که ضرر واقعی این حجم در SL از riskUsd * 1.15 بیشتر نشود ---
      if(riskUsd > 0.0 && slDist > 0.0 && refPrice > 0.0 && volume > minVol)
      {
         double checkProfit = 0.0;
         if(OrderCalcProfit(oType, sym, volume, refPrice, testSL, checkProfit))
         {
            double actualRisk = MathAbs(checkProfit);
            if(actualRisk > (riskUsd * 1.15))
            {
               double safeVol = volume * (riskUsd / actualRisk);
               if(step > 0.0)
                  safeVol = MathFloor((safeVol / step) + 1e-9) * step;
               if(safeVol < minVol) safeVol = minVol;
               volume = NormalizeDouble(safeVol, volDigits);
               Print("🛡️ [ARES FINAL RISK CLAMP]: ActualRisk=$", DoubleToString(actualRisk, 2),
                     " > RiskUSD=$", DoubleToString(riskUsd, 2), " -> SafeVol=", DoubleToString(volume, volDigits));
            }
         }
      }

      double normSL = NormalizeDouble(sl, digits);
      double normTP = NormalizeDouble(tp, digits);

      // --- محاسبه دقیق SL و TP نهایی (2.0R) نسبت به قیمت لحظه‌ای واقعی بروکر ---
      if(slDist > 0.0)
      {
         double effectiveTpDist = (tpDist > 0.0) ? MathMax(tpDist, slDist * 2.0) : (slDist * 2.0);

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
         ok = ExtTrade.Buy(volume, sym, ask, normSL, normTP, orderComment);
         if(!ok && (normSL > 0 || normTP > 0))
         {
            ok = ExtTrade.Buy(volume, sym, ask, 0, 0, orderComment);
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
                        double effTp = (tpDist > 0.0) ? MathMax(tpDist, slDist * 2.0) : (slDist * 2.0);
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
         ok = ExtTrade.Sell(volume, sym, bid, normSL, normTP, orderComment);
         if(!ok && (normSL > 0 || normTP > 0))
         {
            ok = ExtTrade.Sell(volume, sym, bid, 0, 0, orderComment);
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
                        double effTp = (tpDist > 0.0) ? MathMax(tpDist, slDist * 2.0) : (slDist * 2.0);
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

      if(ok && slDist > 0.0)
      {
         for(int p = PositionsTotal() - 1; p >= 0; p--)
         {
            ulong pt = PositionGetTicket(p);
            if(pt > 0 && PositionGetString(POSITION_SYMBOL) == sym)
            {
               GlobalVariableSet("ARES_IV_" + IntegerToString((long)pt), PositionGetDouble(POSITION_VOLUME));
               GlobalVariableSet("ARES_RD_" + IntegerToString((long)pt), slDist);
               GlobalVariableSet("ARES_ST_" + IntegerToString((long)pt), 0.0);
               break;
            }
         }
      }

      Print("🔥 Order Executed [", action, " ", sym, " (raw:", rawSymbol, ") Vol:", volume, " SL:", DoubleToString(normSL, digits), " TP:", DoubleToString(normTP, digits), " Comment:", orderComment, "] Result: ", ok, " Retcode: ", ExtTrade.ResultRetcodeDescription());
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
//| ساخت آرایه JSON کندل‌های یک نماد و تایم‌فریم برای پل ابری       |
//+------------------------------------------------------------------+
string BuildRatesArrayJson(string sym, ENUM_TIMEFRAMES tf, int count)
{
   MqlRates rates[];
   ArraySetAsSeries(rates, false);
   int copied = CopyRates(sym, tf, 0, count, rates);
   if(copied <= 0) return "[]";

   int digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
   if(digits < 0) digits = 5;

   string json = "[";
   for(int i = 0; i < copied; i++)
   {
      if(i > 0) json += ",";
      json += StringFormat(
         "[%I64d,%s,%s,%s,%s,%I64d]",
         (long)rates[i].time,
         DoubleToString(rates[i].open, digits),
         DoubleToString(rates[i].high, digits),
         DoubleToString(rates[i].low, digits),
         DoubleToString(rates[i].close, digits),
         (long)rates[i].tick_volume
      );
   }
   json += "]";
   return json;
}

//+------------------------------------------------------------------+
//| خروجی کندل‌های لحظه‌ای هر ۵ ثانیه (5m/15m/1h/4h/1d + 1m طلا)     |
//+------------------------------------------------------------------+
void ExportLiveCandlesFile()
{
   static datetime lastExportTime = 0;
   static datetime lastSymResolve = 0;
   static string cachedBrokerSyms[4];

   datetime now = TimeLocal();
   if(lastExportTime != 0 && (now - lastExportTime) < 5) return;

   long login = AccountInfoInteger(ACCOUNT_LOGIN);
   if(login <= 0) return;

   string canonicalSyms[4];
   canonicalSyms[0] = "EURUSD";
   canonicalSyms[1] = "XAUUSD";
   canonicalSyms[2] = "NASDAQ 100";
   canonicalSyms[3] = "S&P 500";

   if(lastSymResolve == 0 || (now - lastSymResolve) >= 180)
   {
      int resolvedCount = 0;
      for(int i = 0; i < 4; i++)
      {
         string resolved = ResolveBrokerSymbol(canonicalSyms[i]);
         if(TryActivateSymbol(resolved))
         {
            cachedBrokerSyms[i] = resolved;
            resolvedCount++;
         }
         else
         {
            cachedBrokerSyms[i] = "";
         }
      }
      if(resolvedCount > 0)
         lastSymResolve = now;
   }

   string candlesJson = "{";
   int added = 0;
   for(int i = 0; i < 4; i++)
   {
      string bsym = cachedBrokerSyms[i];
      if(bsym == "") continue;

      string h1Json  = BuildRatesArrayJson(bsym, PERIOD_H1, 50);
      string m15Json = BuildRatesArrayJson(bsym, PERIOD_M15, 60);
      string m5Json  = BuildRatesArrayJson(bsym, PERIOD_M5, 60);
      if(h1Json == "[]" || m15Json == "[]" || m5Json == "[]") continue;

      string h4Json  = BuildRatesArrayJson(bsym, PERIOD_H4, 30);
      string d1Json  = BuildRatesArrayJson(bsym, PERIOD_D1, 20);
      string m1Json  = (canonicalSyms[i] == "XAUUSD") ? BuildRatesArrayJson(bsym, PERIOD_M1, 65) : "[]";
      string safeBsym = SanitizeJsonStr(bsym);

      if(added > 0) candlesJson += ",";
      candlesJson += "\"" + canonicalSyms[i] + "\":{\"broker_symbol\":\"" + safeBsym +
                     "\",\"1h\":" + h1Json + ",\"15m\":" + m15Json + ",\"5m\":" + m5Json +
                     ",\"4h\":" + h4Json + ",\"1d\":" + d1Json + ",\"1m\":" + m1Json + "}";
      added++;
   }
   candlesJson += "}";

   if(added == 0) return;

   string company = SanitizeJsonStr(AccountInfoString(ACCOUNT_COMPANY));
   string server  = SanitizeJsonStr(AccountInfoString(ACCOUNT_SERVER));

   string payload = "{\"login\":" + IntegerToString(login) +
                    ",\"broker\":\"" + company +
                    "\",\"server\":\"" + server +
                    "\",\"candles\":" + candlesJson + "}";

   char postData[];
   int len = StringToCharArray(payload, postData, 0, WHOLE_ARRAY, CP_UTF8);
   if(len > 0) ArrayResize(postData, len - 1);

   int outSize = ArraySize(postData);
   if(outSize > 0)
   {
      int hOut = FileOpen("ares_candles_out.tmp", FILE_WRITE | FILE_BIN);
      if(hOut != INVALID_HANDLE)
      {
         FileWriteArray(hOut, postData, 0, outSize);
         FileClose(hOut);
         FileMove("ares_candles_out.tmp", 0, "ares_candles_out.json", FILE_REWRITE);
      }
   }
   lastExportTime = now;
}

//+------------------------------------------------------------------+
//| خروجی تقویم اقتصادی زنده متاتریدر (actual, forecast, previous)   |
//+------------------------------------------------------------------+
void ExportLiveCalendarFile()
{
   static datetime lastCalExportTime = 0;
   datetime nowLocal = TimeLocal();
   if(lastCalExportTime != 0 && (nowLocal - lastCalExportTime) < 60) return;

   long login = AccountInfoInteger(ACCOUNT_LOGIN);
   if(login <= 0) return;

   datetime serverNow = TimeTradeServer();
   datetime gmtNow    = TimeGMT();
   long gmtOffsetSec  = (long)gmtNow - (long)serverNow;

   MqlCalendarValue values[];
   datetime fromTime = serverNow - 14400; // ۴ ساعت گذشته
   datetime toTime   = serverNow + 7200;  // ۲ ساعت آینده
   int count = CalendarValueHistory(values, fromTime, toTime, NULL, NULL);
   if(count < 0) count = 0;

   string eventsJson = "[";
   int added = 0;

   for(int i = 0; i < count && added < 80; i++)
   {
      MqlCalendarEvent ev;
      if(!CalendarEventById(values[i].event_id, ev)) continue;

      string impStr = "LOW";
      if(ev.importance == CALENDAR_IMPORTANCE_HIGH)
         impStr = "HIGH";
      else if(ev.importance == CALENDAR_IMPORTANCE_MODERATE)
         impStr = "MODERATE";
      else
         continue;

      MqlCalendarCountry country;
      if(!CalendarCountryById(ev.country_id, country)) continue;

      string curr = country.currency;
      StringToUpper(curr);
      if(curr != "USD" && curr != "EUR") continue;

      bool hasActual   = values[i].HasActualValue();
      bool hasForecast = values[i].HasForecastValue();
      bool hasPrev     = values[i].HasPreviousValue();

      double actualVal   = hasActual ? values[i].GetActualValue() : 0.0;
      double forecastVal = hasForecast ? values[i].GetForecastValue() : 0.0;
      double prevVal     = hasPrev ? values[i].GetPreviousValue() : 0.0;

      if(hasActual && !MathIsValidNumber(actualVal))     { hasActual = false; actualVal = 0.0; }
      if(hasForecast && !MathIsValidNumber(forecastVal)) { hasForecast = false; forecastVal = 0.0; }
      if(hasPrev && !MathIsValidNumber(prevVal))         { hasPrev = false; prevVal = 0.0; }

      long utcTs = (long)values[i].time + gmtOffsetSec;
      string safeTitle = SanitizeJsonStr(ev.name);

      if(added > 0) eventsJson += ",";
      eventsJson += "{\"event_id\":" + IntegerToString((long)values[i].event_id) +
                    ",\"currency\":\"" + SanitizeJsonStr(curr) +
                    "\",\"title\":\"" + safeTitle +
                    "\",\"impact\":\"" + impStr +
                    "\",\"time_ts\":" + IntegerToString(utcTs) +
                    ",\"has_actual\":" + (hasActual ? "true" : "false") +
                    ",\"has_forecast\":" + (hasForecast ? "true" : "false") +
                    ",\"has_previous\":" + (hasPrev ? "true" : "false") +
                    ",\"actual\":" + DoubleToString(actualVal, 4) +
                    ",\"forecast\":" + DoubleToString(forecastVal, 4) +
                    ",\"previous\":" + DoubleToString(prevVal, 4) + "}";
      added++;
   }
   eventsJson += "]";

   string company = SanitizeJsonStr(AccountInfoString(ACCOUNT_COMPANY));
   string server  = SanitizeJsonStr(AccountInfoString(ACCOUNT_SERVER));

   string payload = "{\"login\":" + IntegerToString(login) +
                    ",\"broker\":\"" + company +
                    "\",\"server\":\"" + server +
                    "\",\"events\":" + eventsJson + "}";

   char postData[];
   int len = StringToCharArray(payload, postData, 0, WHOLE_ARRAY, CP_UTF8);
   if(len > 0) ArrayResize(postData, len - 1);

   int outSize = ArraySize(postData);
   if(outSize > 0)
   {
      int hOut = FileOpen("ares_calendar_out.tmp", FILE_WRITE | FILE_BIN);
      if(hOut != INVALID_HANDLE)
      {
         FileWriteArray(hOut, postData, 0, outSize);
         FileClose(hOut);
         FileMove("ares_calendar_out.tmp", 0, "ares_calendar_out.json", FILE_REWRITE);
      }
   }
   lastCalExportTime = nowLocal;
}

//+------------------------------------------------------------------+
//| پل ارتباطی محلی فایل برای سرورهای ابری                           |
//+------------------------------------------------------------------+
void SyncViaLocalFileBridge(const char &postData[])
{
   int outSize = ArraySize(postData);
   if(outSize > 0)
   {
      int hOut = FileOpen("ares_sync_out.tmp", FILE_WRITE | FILE_BIN);
      if(hOut != INVALID_HANDLE)
      {
         FileWriteArray(hOut, postData, 0, outSize);
         FileClose(hOut);
         FileMove("ares_sync_out.tmp", 0, "ares_sync_out.json", FILE_REWRITE);
      }
   }

   if(!FileIsExist("ares_sync_proc.json", 0) && FileIsExist("ares_sync_in.json", 0))
   {
      FileMove("ares_sync_in.json", 0, "ares_sync_proc.json", FILE_REWRITE);
   }

   if(FileIsExist("ares_sync_proc.json", 0))
   {
      int hIn = FileOpen("ares_sync_proc.json", FILE_READ | FILE_BIN);
      if(hIn != INVALID_HANDLE)
      {
         int sz = (int)FileSize(hIn);
         if(sz > 0)
         {
            uchar buf[];
            ArrayResize(buf, sz);
            uint readBytes = FileReadArray(hIn, buf, 0, sz);
            FileClose(hIn);
            if(readBytes > 0)
            {
               string resp = CharArrayToString(buf, 0, (int)readBytes, CP_UTF8);
               ProcessServerOrders(resp);
            }
         }
         else
         {
            FileClose(hIn);
         }
         FileDelete("ares_sync_proc.json", 0);
      }
      else
      {
         Print("⚠️ [ARES FILE BRIDGE]: FileOpen failed on ares_sync_proc.json (will retry), err=", GetLastError());
      }
   }
}

//+------------------------------------------------------------------+
//| ساخت جیسون قیمت لحظه‌ای (Bid/Ask) برای تمام نمادهای سیستم       |
//+------------------------------------------------------------------+
string BuildLiveQuotesJson()
{
   static datetime lastQuoteResolve = 0;
   static string qBrokerSyms[4];
   string canonicalSyms[4];
   canonicalSyms[0] = "EURUSD";
   canonicalSyms[1] = "XAUUSD";
   canonicalSyms[2] = "NASDAQ 100";
   canonicalSyms[3] = "S&P 500";

   datetime now = TimeLocal();
   if(lastQuoteResolve == 0 || (now - lastQuoteResolve) >= 180)
   {
      int okCnt = 0;
      for(int i = 0; i < 4; i++)
      {
         string res = ResolveBrokerSymbol(canonicalSyms[i]);
         if(TryActivateSymbol(res))
         {
            qBrokerSyms[i] = res;
            okCnt++;
         }
         else
         {
            qBrokerSyms[i] = "";
         }
      }
      if(okCnt > 0)
         lastQuoteResolve = now;
   }

   string json = "{";
   int added = 0;
   for(int i = 0; i < 4; i++)
   {
      string bsym = qBrokerSyms[i];
      if(bsym == "") continue;
      double bid = SymbolInfoDouble(bsym, SYMBOL_BID);
      double ask = SymbolInfoDouble(bsym, SYMBOL_ASK);
      if(bid <= 0.0) continue;
      if(ask <= 0.0) ask = bid;
      int digits = (int)SymbolInfoInteger(bsym, SYMBOL_DIGITS);
      if(digits < 0) digits = 5;

      if(added > 0) json += ",";
      json += "\"" + canonicalSyms[i] + "\":{\"bid\":" + DoubleToString(bid, digits) +
              ",\"ask\":" + DoubleToString(ask, digits) + "}";
      added++;
   }
   json += "}";
   return json;
}

//+------------------------------------------------------------------+
//| ارسال وضعیت زنده حساب، سود واقعی، پوزیشن‌ها و قیمت ۲ ثانیه‌ای   |
//+------------------------------------------------------------------+
void SyncAccountWithServer()
{
   static int lastWebErr = 0;

   long login = AccountInfoInteger(ACCOUNT_LOGIN);
   if(login <= 0) return;

   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double equity  = AccountInfoDouble(ACCOUNT_EQUITY);
   string company = SanitizeJsonStr(AccountInfoString(ACCOUNT_COMPANY));
   string server  = SanitizeJsonStr(AccountInfoString(ACCOUNT_SERVER));

   double initialDeposit = 0.0;
   double historyPnL     = CalculateRealHistoryPnL(initialDeposit);
   double floatingPnL    = 0.0;
   string openPosJson    = BuildOpenPositionsJson(floatingPnL);
   string activeSymsJson = BuildActiveSymbolsJson();
   string liveQuotesJson = BuildLiveQuotesJson();
   string ackedCmdsJson  = BuildAckedCmdsJson();

   string ident = (InpUserIdentifier != "") ? InpUserIdentifier : IntegerToString(login);

   string payload = StringFormat(
      "{\"identifier\":\"%s\",\"login\":%I64d,\"balance\":%.2f,\"equity\":%.2f,\"history_pnl\":%.2f,\"floating_pnl\":%.2f,\"initial_deposit\":%.2f,\"broker\":\"%s\",\"server\":\"%s\",\"verified_symbols\":true,\"open_positions\":%s,\"active_symbols\":%s",
      ident, login, balance, equity, historyPnL, floatingPnL, initialDeposit, company, server, openPosJson, activeSymsJson
   ) + ",\"live_quotes\":" + liveQuotesJson + ",\"acked_cmds\":" + ackedCmdsJson + "}";

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
         Print("⚠️ [ARES Sync Fallback] HTTP=", res, " LastError=", err, " -> Using Local File Bridge");
      }
      SyncViaLocalFileBridge(postData);
   }
}
//+------------------------------------------------------------------+