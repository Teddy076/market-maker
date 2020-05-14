# encoding=utf-8
import sys
from time import sleep
from market_maker.utils import math, log
from market_maker.settings import settings
from market_maker.market_maker import OrderManager
from indexprice.indexprice import IndexPrice
from market_maker.binance.binance.client import Client

#client = Client(syYwiP5hThosU9IE4bAVUBfsJcmTXewBjPhqmMHjP8ppZC6PzihwqyS4fwS1EYVb, dUyaibou5dbU1wREWeH9MNKTK50KCRFF5NsgR5vQWQguNIPMCZRuflo6P6VUtAPm)
client = Client(settings.API_KEY, settings.API_SECRET)
logger = log.setup_custom_logger('custom_binance')

offset = []
indexprice_list = []
orders = {}
list_buy_qty = []
list_buy_amount = []
list_sell_qty = []
list_sell_amount = []

# ##################################################################
# ########################### TO-DO-LIST ###########################
# ##################################################################
# 1 - Maintain spread gestion paramètre


class SpotMM:
    def __init__(self):
        self.current_position = 0
        self.total_volume = 0

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
        openorder = ''

        # IndexPrice
        indexprice = IndexPrice().LastPrice(settings.SYMBOL)

        # Prediction : Liste des IndexPrice
        indexprice_list.append(indexprice)
        if len(indexprice_list) > settings.PREDICT_SIZE:
            del indexprice_list[0]

        # Exchange Data
        ticker = client.get_orderbook_ticker(symbol=settings.SYMBOL)
        ticker_bid = float(ticker["bidPrice"])
        ticker_ask = float(ticker["askPrice"])
        ticker_mid = (ticker_bid + ticker_ask) / 2
        logger.info('Ticker Mid : ' + str(ticker_mid))
        #current_position = self.exchange.get_delta()

        # Offset List
        offset.append(((ticker_mid - indexprice) / indexprice))
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
        if settings.PREDICT_MODE != 0:
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
        #logger.debug('Taille Offset : ' + str(len(offset)))
        #logger.debug(str(offset))
        logger.info('Offset calculé : ' + str(round(offset_calcul * 100, settings.ROUND_PRECISION)))
        logger.info('IndexPrice avec offset : ' + str(round(indexoffset, settings.ROUND_PRECISION)))

        if settings.PREDICT_MODE != 0:
            logger.info('Prediction : ' + str(round(predict_delta, settings.ROUND_PRECISION)))

            # Application de la Prediction à indexoffset
            indexoffset += predict_delta

            logger.info('IndexPrice avec predict : ' + str(round(indexoffset, settings.ROUND_PRECISION)))

        # Customisation du TickSize
        if settings.TICKSIZE_CUSTOM != 0:
            ticksize = settings.TICKSIZE_CUSTOM
        else:
            ticksize = 0.01

        # Boucle d'ajout des ordres
        for i in range (0, settings.ORDER_PAIRS):
            # RAZ Variables
            buyprice = 0
            sellprice = 0
            res_buy = ''
            res_sell = ''
            nochange_buy = 0
            nochange_sell = 0

            # #########################################################################################################
            # #############################################     BUY     ###############################################
            # #########################################################################################################
            if self.current_position < settings.MAX_POSITION:
                # Premier passage, on check le spread et on applique le MIN_SPREAD
                if i == 0:
                    # Price Calculation
                    buyprice = math.toNearest(indexoffset * (1 - (settings.MIN_SPREAD / 2)), ticksize)

                    # MAINTAIN_SPREADS
                    if buyprice > ticker_bid and settings.MAINTAIN_SPREADS == True: buyprice = ticker_bid

                # Palier
                if buyprice_last > 0:
                    buyprice = math.toNearest(buyprice_last * (1 - (settings.INTERVAL * (i + 1))), ticksize)
                buyprice_last = buyprice

                # Si nous ne connaissons pas encore ce palier
                if 'BUY_' + str(i) not in orders:
                    # Si nous ne connaissons pas encore ce palier, on passe notre ordre
                    res_buy = client.order_limit_buy(
                        symbol=settings.SYMBOL,
                        quantity=(settings.ORDER_START_SIZE + (settings.ORDER_STEP_SIZE * i)),
                        price=buyprice)
                else:
                    # On connait le palier, on le check
                    if orders['BUY_' + str(i)]["price"] != buyprice:
                        # Avant de supprimer, on check qu'il est encore en cours
                        logger.debug(orders['BUY_' + str(i)])
                        try:
                            res_del_check = client.get_order(
                                symbol=settings.SYMBOL,
                                orderId=orders['BUY_' + str(i)]["orderId"])

                            if res_del_check["status"] in ('FILLED','CANCELED'):
                                # Ordre filled, on récupère le executedQty
                                if float(res_del_check["executedQty"]) > 0:
                                    self.current_position += float(res_del_check["executedQty"])
                                    self.total_volume += float(res_del_check["executedQty"])
                                    list_buy_qty.append(float(res_del_check["executedQty"]))
                                    list_buy_amount.append(float(res_del_check["executedQty"]) * orders['BUY_' + str(i)]["price"])
                                    #list_buy.append([orders['BUY_' + str(i)]["price"], res_del_check["executedQty"]])
                                    logger.info('*** EXECUTION BUY Check *** : ' + res_del_check["executedQty"])
                            else:
                                # On supprime l'ordre précedent
                                try:
                                    res_del_buy = client.cancel_order(
                                        symbol=settings.SYMBOL,
                                        orderId=orders['BUY_' + str(i)]["orderId"])
                                    #logger.debug(res_del_buy)

                                    # On récupère le montant éxecuté
                                    # On le fait exclusivement ici afin de ne pas double comptabiliser des partial-filled
                                    if float(res_del_buy["executedQty"]) > 0:
                                        self.current_position += float(res_del_buy["executedQty"])
                                        self.total_volume += float(res_del_buy["executedQty"])
                                        list_buy_qty.append(float(res_del_buy["executedQty"]))
                                        list_buy_amount.append(float(res_del_buy["executedQty"]) * orders['BUY_' + str(i)]["price"])
                                        #list_buy.append([orders['BUY_' + str(i)]["price"], res_del_buy["executedQty"]])
                                        logger.info('*** EXECUTION BUY Cancel *** : ' + res_del_buy["executedQty"])
                                except:
                                    logger.info('EXCEPTION lors du Cancel BUY_'+str(i))

                            # Ajout du nouvel ordre
                            res_buy = client.order_limit_buy(
                                symbol=settings.SYMBOL,
                                quantity=(settings.ORDER_START_SIZE + (settings.ORDER_STEP_SIZE * i)),
                                price=buyprice)
                        except:
                            logger.info('EXCEPTION lors du Check BUY_'+str(i))
                            nochange_buy = 1

                    else:
                        # Pas de changement, on ne touche a rien
                        nochange_buy = 1

                if nochange_buy == 0:
                    # On ajoute ou remplace l'élément
                    orders['BUY_' + str(i)] = {'orderId': res_buy["orderId"], 'price': buyprice}
                    logger.info('ORDER BUY_' + str(i) + ' Added : Price=' + str(buyprice))

                    if float(res_buy["executedQty"]) != 0:
                        # Filled
                        logger.info('*** EXECUTION BUY Order TAKER *** : ' + str(res_buy["executedQty"]))
            else:
                # MAX_POSITION Atteint, on check si on a un ordre en cours, si oui on le supprime
                if 'BUY_' + str(i) in orders:
                    try:
                        res_del_buy = client.cancel_order(
                            symbol=settings.SYMBOL,
                            orderId=orders['BUY_' + str(i)]["orderId"])

                        # On récupère le montant éxecuté
                        # On le fait exclusivement ici afin de ne pas double comptabiliser des partial-filled
                        if float(res_del_buy["executedQty"]) > 0:
                            self.current_position += float(res_del_buy["executedQty"])
                            self.total_volume += float(res_del_buy["executedQty"])
                            list_buy_qty.append(float(res_del_buy["executedQty"]))
                            list_buy_amount.append(float(res_del_buy["executedQty"]) * orders['BUY_' + str(i)]["price"])
                            #list_buy.append([orders['BUY_' + str(i)]["price"], res_del_buy["executedQty"]])
                            logger.info('*** EXECUTION BUY Cancel MAX_POS *** : ' + res_del_buy["executedQty"])
                    except:
                        logger.info('EXCEPTION lors du Cancel MAX_POS BUY_'+str(i))
                        del orders['BUY_' + str(i)]

            # #########################################################################################################
            # #############################################     SELL     ##############################################
            # #########################################################################################################
            if self.current_position > settings.MIN_POSITION:
                # Premier passage, on check le spread et on applique le MIN_SPREAD
                if i == 0:
                    # Price Calculation
                    sellprice = math.toNearest(indexoffset * (1 + (settings.MIN_SPREAD / 2)), ticksize)

                    # MAINTAIN_SPREADS
                    if sellprice < ticker_ask and settings.MAINTAIN_SPREADS == True: sellprice = ticker_ask

                # Palier
                if sellprice_last > 0:
                    sellprice = math.toNearest(sellprice_last * (1 + (settings.INTERVAL * (i + 1))), ticksize)
                sellprice_last = sellprice

                # Si nous ne connaissons pas encore ce palier
                if 'SELL_' + str(i) not in orders:
                    # Si nous ne connaissons pas encore ce palier, on passe notre ordre
                    res_sell = client.order_limit_sell(
                        symbol=settings.SYMBOL,
                        quantity=(settings.ORDER_START_SIZE + (settings.ORDER_STEP_SIZE * i)),
                        price=sellprice)
                else:
                    # On connait le palier, on le check
                    if orders['SELL_' + str(i)]["price"] != sellprice:
                        # Avant de supprimer, on check qu'il est encore en cours
                        res_del_check = client.get_order(
                            symbol=settings.SYMBOL,
                            orderId=orders['SELL_' + str(i)]["orderId"])
                        #logger.debug(res_del_check)
                        if res_del_check["status"] in ('FILLED','CANCELED'):
                            # Ordre filled, on récupère le executedQty
                            if float(res_del_check["executedQty"]) > 0:
                                self.current_position -= float(res_del_check["executedQty"])
                                self.total_volume += float(res_del_check["executedQty"])
                                list_sell_qty.append(float(res_del_check["executedQty"]))
                                list_sell_amount.append(float(res_del_check["executedQty"]) * orders['SELL_' + str(i)]["price"])
                                #list_sell.append([orders['SELL_' + str(i)]["price"], res_del_check["executedQty"]])
                                logger.info('*** EXECUTION SELL Check *** : ' + res_del_check["executedQty"])
                        else:
                            # On supprime l'ordre précedent
                            try:
                                res_del_sell = client.cancel_order(
                                    symbol=settings.SYMBOL,
                                    orderId=orders['SELL_' + str(i)]["orderId"])
                                #logger.debug(res_del_sell)

                                # On récupère le montant éxecuté
                                # On le fait exclusivement ici afin de ne pas double comptabiliser des partial-filled
                                if float(res_del_sell["executedQty"]) > 0:
                                    self.current_position -= float(res_del_sell["executedQty"])
                                    self.total_volume += float(res_del_sell["executedQty"])
                                    list_sell_qty.append(float(res_del_sell["executedQty"]))
                                    list_sell_amount.append(float(res_del_sell["executedQty"]) * orders['SELL_' + str(i)]["price"])
                                    #list_sell.append([orders['SELL_' + str(i)]["price"], res_del_sell["executedQty"]])
                                    logger.info('*** EXECUTION SELL Cancel *** : ' + res_del_sell["executedQty"])
                            except:
                                logger.info('EXCEPTION lors du Cancel SELL_'+str(i))

                        # Ajout du nouvel ordre
                        res_sell = client.order_limit_sell(
                            symbol=settings.SYMBOL,
                            quantity=(settings.ORDER_START_SIZE + (settings.ORDER_STEP_SIZE * i)),
                            price=sellprice)
                    else:
                        # Pas de changement, on ne touche a rien
                        nochange_sell = 1

                if nochange_sell == 0:
                    # On ajoute ou remplace l'élément
                    orders['SELL_' + str(i)] = {'orderId': res_sell["orderId"], 'price': sellprice}
                    logger.info('ORDER SELL_' + str(i) + ' Added : Price=' + str(sellprice))

                    if float(res_sell["executedQty"]) != 0:
                        # Filled
                        logger.info('*** EXECUTION SELL Order TAKER *** : ' + str(res_sell["executedQty"]))
            else:
                # MIN_POSITION Atteint, on check si on a un ordre en cours, si oui on le supprime
                if 'SELL_' + str(i) in orders:
                    try:
                        res_del_sell = client.cancel_order(
                            symbol=settings.SYMBOL,
                            orderId=orders['SELL_' + str(i)]["orderId"])
                        #logger.debug(res_del_sell)

                        # On récupère le montant éxecuté
                        # On le fait exclusivement ici afin de ne pas double comptabiliser des partial-filled
                        if float(res_del_sell["executedQty"]) > 0:
                            self.current_position -= float(res_del_sell["executedQty"])
                            self.total_volume += float(res_del_sell["executedQty"])
                            list_sell_qty.append(float(res_del_sell["executedQty"]))
                            list_sell_amount.append(float(res_del_sell["executedQty"]) * orders['SELL_' + str(i)]["price"])
                            #list_sell.append([orders['SELL_' + str(i)]["price"], res_del_sell["executedQty"]])
                            logger.info('*** EXECUTION SELL Cancel MIN_POS *** : ' + res_del_sell["executedQty"])
                    except:
                        logger.info('EXCEPTION lors du Cancel MIN_POS SELL_'+str(i))
                        del orders['SELL_' + str(i)]

        if len(list_buy_qty) > 0:
            logger.info('Avg Buy Price : ' + str(round(sum(list_buy_amount)/sum(list_buy_qty), settings.ROUND_PRECISION)))
            logger.info('Volume Buy : ' + str(sum(list_buy_qty)))
        if len(list_sell_qty) > 0:
            logger.info('Avg Sell Price : ' + str(round(sum(list_sell_amount)/sum(list_sell_qty), settings.ROUND_PRECISION)))
            logger.info('Volume Sell : ' + str(sum(list_sell_qty)))
        if len(list_buy_qty) > 0 and len(list_sell_qty) > 0:
            if sum(list_buy_qty) < sum(list_sell_qty):
                logger.info('Benefice : ' + str(round(((sum(list_sell_amount)/sum(list_sell_qty)) * sum(list_buy_qty)) - ((sum(list_buy_amount)/sum(list_buy_qty)) * sum(list_buy_qty)), settings.ROUND_PRECISION)))
            else:
                logger.info('Benefice : ' + str(round(((sum(list_sell_amount)/sum(list_sell_qty)) * sum(list_sell_qty)) - ((sum(list_buy_amount)/sum(list_buy_qty)) * sum(list_sell_qty)), settings.ROUND_PRECISION)))
        logger.info('Position en cours : ' + str(round(self.current_position, settings.ROUND_PRECISION)))
        logger.info('Volume Total : ' + str(round(self.total_volume, settings.ROUND_PRECISION)))

        logger.debug(orders)


def run() -> None:
    # Try/except just keeps ctrl-c from printing an ugly stacktrace
    try:
        mm = SpotMM()
        while True:
            mm.place_orders()

            sys.stdout.write("-----\n")
            sys.stdout.flush()

            sleep(settings.LOOP_INTERVAL)

            # This will restart on very short downtime, but if it's longer,
            # the MM will crash entirely as it is unable to connect to the WS on boot.
            #if not self.check_connection():
            #    logger.error("Realtime data connection unexpectedly closed, restarting.")
            #    self.restart()
    except (KeyboardInterrupt, SystemExit):
        # Delete des orders
        for i in orders:
            # On supprime l'ordre
            res_del = client.cancel_order(
                symbol=settings.SYMBOL,
                orderId=orders[i]["orderId"])
            logger.debug(res_del)

            # On récupère le montant éxecuté
            if float(res_del["executedQty"]) > 0:
                if res_del["side"] == "BUY":
                    current_position += float(res_del["executedQty"])
                    logger.info('EXECUTION BUY : ' + res_del["executedQty"])
                else:
                    current_position -= float(res_del["executedQty"])
                    logger.info('EXECUTION SELL : ' + res_del["executedQty"])

        logger.info('Position finale : ' + str(mm.current_position))

        sys.exit()
