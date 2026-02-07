/*
 * Bridge para NinjaTrader 8
 * Conecta estrategias de NT8 con Aethelgard via WebSocket
 * 
 * Instrucciones:
 * 1. Copiar este archivo a la carpeta de estrategias de NinjaTrader 8
 * 2. Compilar en NT8
 * 3. Configurar la URL del servidor Aethelgard en OnStateChange()
 */

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.SuperDom;
using NinjaTrader.Gui.Tools;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.Core.FloatingPoint;
using NinjaTrader.NinjaScript.Indicators;
using NinjaTrader.NinjaScript.DrawingTools;
using System.Net.WebSockets;
using System.Threading;
using Newtonsoft.Json;
#endregion

namespace NinjaTrader.NinjaScript.Strategies
{
    public class AethelgardBridge : Strategy
    {
        #region Variables
        private ClientWebSocket webSocket;
        private CancellationTokenSource cancellationTokenSource;
        private string serverUrl = "ws://localhost:8000/ws/NT/";
        private string clientId;
        private bool isConnected = false;
        #endregion

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = @"Bridge para conectar estrategias NT8 con Aethelgard";
                Name = "AethelgardBridge";
                Calculate = Calculate.OnBarClose;
                EntriesPerDirection = 1;
                EntryHandling = EntryHandling.AllEntries;
                IsExitOnSessionCloseStrategy = true;
                ExitOnSessionCloseSeconds = 30;
                IsFillLimitOnTouch = false;
                MaximumBarsLookBack = MaximumBarsLookBack.TwoHundredFiftySix;
                OrderFillResolution = OrderFillResolution.Standard;
                Slippage = 0;
                StartBehavior = StartBehavior.WaitUntilFlat;
                TimeInForce = TimeInForce.Gtc;
                TraceOrders = false;
                RealtimeErrorHandling = RealtimeErrorHandling.StopCancelClose;
                StopTargetHandling = StopTargetHandling.PerEntryExecution;
                BarsRequiredToTrade = 20;
                IsInstantiatedOnEachOptimizationIteration = true;
                
                // Parámetros configurables
                ServerUrl = "ws://localhost:8000/ws/NT/";
                ClientId = "NT8_" + System.Environment.MachineName;
            }
            else if (State == State.Configure)
            {
                // Configurar aquí parámetros adicionales si es necesario
            }
            else if (State == State.Active)
            {
                // Conectar al servidor Aethelgard
                ConnectToAethelgard();
            }
            else if (State == State.Terminated)
            {
                // Desconectar del servidor
                DisconnectFromAethelgard();
            }
        }

        protected override void OnBarUpdate()
        {
            // Este método se ejecuta en cada barra
            // Aquí puedes añadir lógica para enviar datos de mercado a Aethelgard
            if (isConnected && CurrentBar >= BarsRequiredToTrade)
            {
                SendMarketData();
            }
        }

        protected override void OnExecutionUpdate(Execution execution, string executionId, double price, int quantity, 
            MarketPosition marketPosition, string orderId, DateTime time)
        {
            // Enviar actualizaciones de ejecución a Aethelgard
            if (isConnected)
            {
                SendExecutionUpdate(execution, price, quantity, marketPosition, orderId, time);
            }
        }

        #region Métodos de Conexión WebSocket

        private async void ConnectToAethelgard()
        {
            try
            {
                webSocket = new ClientWebSocket();
                cancellationTokenSource = new CancellationTokenSource();
                
                string fullUrl = ServerUrl + ClientId;
                Print($"Conectando a Aethelgard: {fullUrl}");
                
                await webSocket.ConnectAsync(new Uri(fullUrl), cancellationTokenSource.Token);
                isConnected = true;
                
                Print("Conectado a Aethelgard exitosamente");
                
                // Iniciar hilo para recibir mensajes
                Task.Run(() => ReceiveMessages(cancellationTokenSource.Token));
                
                // Enviar mensaje de inicialización
                SendMessage(new
                {
                    type = "init",
                    client_id = ClientId,
                    symbol = Instrument.FullName,
                    timestamp = DateTime.UtcNow.ToString("o")
                });
            }
            catch (Exception ex)
            {
                Print($"Error conectando a Aethelgard: {ex.Message}");
                isConnected = false;
            }
        }

        private async void DisconnectFromAethelgard()
        {
            try
            {
                isConnected = false;
                cancellationTokenSource?.Cancel();
                
                if (webSocket != null && webSocket.State == WebSocketState.Open)
                {
                    await webSocket.CloseAsync(WebSocketCloseStatus.NormalClosure, 
                        "Closing", CancellationToken.None);
                }
                
                webSocket?.Dispose();
                Print("Desconectado de Aethelgard");
            }
            catch (Exception ex)
            {
                Print($"Error desconectando de Aethelgard: {ex.Message}");
            }
        }

        private async void ReceiveMessages(CancellationToken cancellationToken)
        {
            var buffer = new byte[1024 * 4];
            
            while (webSocket.State == WebSocketState.Open && !cancellationToken.IsCancellationRequested)
            {
                try
                {
                    var result = await webSocket.ReceiveAsync(new ArraySegment<byte>(buffer), cancellationToken);
                    
                    if (result.MessageType == WebSocketMessageType.Text)
                    {
                        string message = Encoding.UTF8.GetString(buffer, 0, result.Count);
                        ProcessMessage(message);
                    }
                    else if (result.MessageType == WebSocketMessageType.Close)
                    {
                        await webSocket.CloseAsync(WebSocketCloseStatus.NormalClosure, 
                            "Closed by server", CancellationToken.None);
                        isConnected = false;
                        break;
                    }
                }
                catch (Exception ex)
                {
                    Print($"Error recibiendo mensaje: {ex.Message}");
                    break;
                }
            }
        }

        private void ProcessMessage(string message)
        {
            try
            {
                dynamic data = JsonConvert.DeserializeObject(message);
                string messageType = data.type;
                
                if (messageType == "signal_processed")
                {
                    Print($"Señal procesada por Aethelgard. ID: {data.signal_id}, Régimen: {data.regime}");
                }
                else if (messageType == "execute_signal")
                {
                    ExecuteRemoteSignal(data);
                }
                else if (messageType == "pong")
                {
                    // Heartbeat response
                }
                else if (messageType == "error")
                {
                    Print($"Error de Aethelgard: {data.message}");
                }
            }
            catch (Exception ex)
            {
                Print($"Error procesando mensaje: {ex.Message}");
            }
        }

        private void ExecuteRemoteSignal(dynamic data)
        {
            try
            {
                string signalType = data.signal_type;
                double price = data.price;
                int quantity = data.volume ?? Quantity;
                double? sl = data.stop_loss;
                double? tp = data.take_profit;

                Print($"EJECUCIÓN REMOTA RECIBIDA: {signalType} @ {price}");

                if (signalType == "BUY")
                {
                    EnterLong(quantity, "Aethelgard_Long");
                    if (sl.HasValue) SetStopLoss("Aethelgard_Long", CalculationMode.Price, sl.Value, false);
                    if (tp.HasValue) SetProfitTarget("Aethelgard_Long", CalculationMode.Price, tp.Value, false);
                }
                else if (signalType == "SELL")
                {
                    EnterShort(quantity, "Aethelgard_Short");
                    if (sl.HasValue) SetStopLoss("Aethelgard_Short", CalculationMode.Price, sl.Value, false);
                    if (tp.HasValue) SetProfitTarget("Aethelgard_Short", CalculationMode.Price, tp.Value, false);
                }
                else if (signalType == "EXIT")
                {
                    ExitPosition("Aethelgard_Exit", "");
                }
            }
            catch (Exception ex)
            {
                Print($"Error ejecutando señal remota: {ex.Message}");
            }
        }

        private async void SendMessage(object data)
        {
            if (!isConnected || webSocket.State != WebSocketState.Open)
                return;
            
            try
            {
                string json = JsonConvert.SerializeObject(data);
                byte[] buffer = Encoding.UTF8.GetBytes(json);
                
                await webSocket.SendAsync(new ArraySegment<byte>(buffer), 
                    WebSocketMessageType.Text, true, CancellationToken.None);
            }
            catch (Exception ex)
            {
                Print($"Error enviando mensaje: {ex.Message}");
                isConnected = false;
            }
        }

        #endregion

        #region Métodos de Envío de Datos

        private void SendMarketData()
        {
            if (CurrentBar < 1) return;
            
            SendMessage(new
            {
                type = "market_data",
                symbol = Instrument.FullName,
                price = Close[0],
                high = High[0],
                low = Low[0],
                volume = Volume[0],
                timestamp = Time[0].ToString("o")
            });
        }

        private void SendSignal(string signalType, double price, double? stopLoss = null, double? takeProfit = null)
        {
            SendMessage(new
            {
                type = "signal",
                connector = "NT",
                symbol = Instrument.FullName,
                signal_type = signalType,
                price = price,
                timestamp = DateTime.UtcNow.ToString("o"),
                volume = Quantity,
                stop_loss = stopLoss,
                take_profit = takeProfit,
                metadata = new
                {
                    account = Account.Name,
                    strategy = Name
                }
            });
        }

        private void SendExecutionUpdate(Execution execution, double price, int quantity, 
            MarketPosition marketPosition, string orderId, DateTime time)
        {
            SendMessage(new
            {
                type = "execution",
                symbol = Instrument.FullName,
                price = price,
                quantity = quantity,
                market_position = marketPosition.ToString(),
                order_id = orderId,
                timestamp = time.ToString("o")
            });
        }

        #endregion

        #region Properties

        [NinjaScriptProperty]
        [Display(Name = "Server URL", Description = "URL del servidor Aethelgard", Order = 1, GroupName = "Aethelgard")]
        public string ServerUrl
        { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Client ID", Description = "ID único del cliente", Order = 2, GroupName = "Aethelgard")]
        public string ClientId
        { get; set; }

        #endregion
    }
}
