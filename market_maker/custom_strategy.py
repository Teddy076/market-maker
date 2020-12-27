# encoding=utf-8
import sys
from market_maker.utils import math, log
from market_maker.settings import settings
from market_maker.market_maker import OrderManager
from indexprice.indexprice import IndexPrice

logger = log.setup_custom_logger('custom')

offset = []
indexprice_list = []

# ##################################################################
# ########################### TO-DO-LIST ###########################
# ##################################################################
# 1 - Maintain spread gestion paramètre




class CustomOrderManager(OrderManager):
    """A sample order manager for implementing your own custom strategy"""

    def place_orders(self) -> None:
        buy_orders = []
        sell_orders = []
        buyprice_last = 0
        sellprice_last = 0
        offset_cumul = 0
        offset_coef = 0
        predict_delta = 0
        predict_cumul = 0
        predict_last = 0
        tickSize = 0

        # IndexPrice
        if settings.SYMBOL2 != "":
            # Mode Double SYMBOL
            indexprice = IndexPrice().LastPrice(settings.SYMBOL1) / IndexPrice().LastPrice(settings.SYMBOL2)
        else:
            indexprice = IndexPrice().LastPrice(settings.SYMBOL)

        # Prediction : Liste des IndexPrice
        indexprice_list.append(indexprice)
        if len(indexprice_list) > settings.PREDICT_SIZE:
            del indexprice_list[0]

        # BitMEX Data
        ticker = self.exchange.get_ticker()
        current_position = self.exchange.get_delta()

        # Offset List
        offset.append(((ticker["mid"] - indexprice) / indexprice))
        if len(offset) > settings.OFFSET_MAX:
            del offset[0]

        # Calcul de l'offset à appliquer
        # On accorde plus d'importance aux données récentes selon certains settings
        for i in range(0, len(offset)):
            offset_cumul += (offset[i] * (i + 1))
            offset_coef += (i + 1)

        # Calcul offset final
        # On obtient un pourcentage brut à appliquer à notre indexprice
        offset_calcul = (offset_cumul / offset_coef)
        indexoffset = indexprice * (1 + offset_calcul)

        # Prediction
        for i in range(0, len(indexprice_list)):
            if predict_last > 0:
                predict_cumul += (indexprice_list[i] - predict_last)
            predict_last = indexprice_list[i]

        # Prediction Mode
        if settings.PREDICT_MODE == 1:
            # Cumul
            predict_delta = predict_cumul
        elif settings.PREDICT_MODE == 2:
            # Moyenne
            predict_delta = (predict_cumul / settings.PREDICT_SIZE)
        else:
            # Inconnu : On utilise le mode par défault et indique un warning
            logger.warning('Please check settings : PREDICT_MODE is wrong')
            predict_delta = predict_cumul

        # Log some data
        logger.debug('Taille Offset : ' + str(len(offset)))
        logger.debug(str(offset))
        logger.info('Offset calculé : ' + str(round(offset_calcul * 100, settings.ROUND_PRECISION)))
        logger.info('IndexPrice avec offset : ' + str(round(indexoffset, settings.ROUND_PRECISION)))
        logger.info('Prediction : ' + str(round(predict_delta, settings.ROUND_PRECISION)))

        # Application de la Prediction à indexoffset
        indexoffset += predict_delta

        logger.info('IndexPrice avec predict : ' + str(round(indexoffset, settings.ROUND_PRECISION)))

        # Customisation du TickSize
        if settings.TICKSIZE_CUSTOM != 0:
            ticksize = settings.TICKSIZE_CUSTOM
        else:
            ticksize = self.instrument['tickSize']

        # Boucle d'ajout des ordres
        for i in range (0, settings.ORDER_PAIRS):
            # RAZ Variables
            buyprice = 0
            sellprice = 0

            # BUY
            if current_position < settings.MAX_POSITION:
                # Premier passage, on check le spread et on applique le MIN_SPREAD
                if i == 0:
                    # Price Calculation
                    buyprice = math.toNearest(indexoffset * (1 - (settings.MIN_SPREAD / 2)), ticksize)

                    # MAINTAIN_SPREADS
                    if buyprice > ticker['buy'] and settings.MAINTAIN_SPREADS == True: buyprice = ticker['buy']

                # Palier
                if buyprice_last > 0:
                    buyprice = math.toNearest(buyprice_last * (1 - (settings.INTERVAL * (i + 1))), ticksize)
                buyprice_last = buyprice

                buy_orders.append({'price': float(buyprice), 'orderQty': (settings.ORDER_START_SIZE + (settings.ORDER_STEP_SIZE * i)), 'side': "Buy"})

            # SELL
            if current_position > settings.MIN_POSITION:
                # Premier passage, on check le spread et on applique le MIN_SPREAD
                if i == 0:
                    # Price Calculation
                    sellprice = math.toNearest(indexoffset * (1 + (settings.MIN_SPREAD / 2)), ticksize)

                    # MAINTAIN_SPREADS
                    if sellprice < ticker['sell'] and settings.MAINTAIN_SPREADS == True: sellprice = ticker['sell']

                # Palier
                if sellprice_last > 0:
                    sellprice = math.toNearest(sellprice_last * (1 + (settings.INTERVAL * (i + 1))), ticksize)
                sellprice_last = sellprice

                sell_orders.append({'price': float(sellprice), 'orderQty': (settings.ORDER_START_SIZE + (settings.ORDER_STEP_SIZE * i)), 'side': "Sell"})

        # Exemples de base
        # populate buy and sell orders, e.g.
        #buy_orders.append({'price': float(buyprice1), 'orderQty': 100, 'side': "Buy"})
        #sell_orders.append({'price': float(sellprice1), 'orderQty': 100, 'side': "Sell"})

        self.converge_orders(buy_orders, sell_orders)


def run() -> None:
    order_manager = CustomOrderManager()

    # Try/except just keeps ctrl-c from printing an ugly stacktrace
    try:
        order_manager.run_loop()
    except (KeyboardInterrupt, SystemExit):
        sys.exit()
