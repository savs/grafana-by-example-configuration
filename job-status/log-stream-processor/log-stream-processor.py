#
import os
import json
import pprint
import requests
import time

# Flask
from flask import Flask
from flask import request

# Prometheus Client
import prometheus_client as pclient

# Disabling Default Collector metrics
pclient.REGISTRY.unregister(pclient.GC_COLLECTOR)
pclient.REGISTRY.unregister(pclient.PLATFORM_COLLECTOR)
pclient.REGISTRY.unregister(pclient.PROCESS_COLLECTOR)

# Create the Promethues Metrics
metric1 = pclient.Gauge("test_xyz", "Number", ["region", "service"] )
metric2 = pclient.Counter("test_ingest_events", "Total ingest events" )
metric3 = pclient.Info("test_service_version", "Version Information")

# Loki Config
try:
    lokiWriteURL = "{a}://{u}:{k}@{h}:{p}{x}".format(
                        a=os.environ["GRAFANA_LOGS_PROTOCOL"],
                        u=os.environ["GRAFANA_LOGS_USERNAME"],
                        k=os.environ["GRAFANA_LOGS_API_KEY"],
                        h=os.environ["GRAFANA_LOGS_HOST"],
                        p=os.environ["GRAFANA_LOGS_PORT"],
                        x="/loki/api/v1/push")
    print( "Remote write to loki configured: {}".format(lokiWriteURL))
except Exception as e:
    print( "Environment variable not set: {}".format(e))
    lokiWriteURL = ""
    print( "Remote write to loki not configured")

# https://grafana.com/docs/loki/latest/api/#push-log-entries-to-loki
def lokiWriteStreams(logStreams):
    if lokiWriteURL != "":
        try:
            #nowNs = int(time.time() * 1000000000)
            #stream = {
            #    "stream": logLabels,
            #    "values": [
            #        [str(nowNs), logMessageStr]
            #    ]
            #}
            #print( "stream < {} >".format( stream ) )
            #lokiData = { "streams": stream }
            headers = { "Content-Type": "application/json" }
            data = json.JSONEncoder().encode(logStreams)
            s = requests.session()
            r = s.post(lokiWriteURL, headers=headers, data=data)
            if not r.ok:
                print(data)
                print(r.ok)
                print(r.text)
                print(r.status_code)
        except Exception as e:
            print(e)

# Ports
prometheusHttpPort = int( os.environ.get('PROMTHEUS_HTTP_PORT', 9001) )
#flaskHttpPort = int( os.environ.get('FASK_HTTP_PORT', 9002) )

# json: {'streams': [{'stream': {'job': 'test2', 'state': 'success'}, 'values': [['1683424065903416064', '{"name": "jobA", "state": "success", "ts": 1683424065}']]}]}

# Hashmap of metrics
jobList = {}

# Log stream processor
def handleLogStream(streams):
    for stream in streams:
        streamLabels = stream["stream"]
        #print("S s{} v{}".format( stream["stream"], stream["values"]) )
        for m in stream["values"]:
            ts, lm = m # time stamp, log messages
            jlm = json.loads( lm )
            metricNameBase = "job{}".format(jlm["state"])
            metricLabels = "{}-{}".format( jlm["name"], jlm["state"] )
            metricNameKey = "{}-{}".format( metricNameBase, metricLabels )
            metricNameKey = "{}".format( jlm["name"] )
            if metricNameKey in jobList.keys(): # Update Metrics
                mlm =  jobList[metricNameKey]["metrics"]
                mlm["total_state_counter"].labels(name=jlm["name"],state=jlm["state"]).inc()
                mlm["timeInState"].labels(name=jlm["name"],state=jlm["state"]).set(jlm["ts"] - mlm["lastStateTs"])
                if mlm["lastState"] != jlm["state"]:  # Update metrics  on state change
                    mlm["stateTimeSec"].labels(name=jlm["name"], state=jlm["state"] ).inc(jlm["ts"] - mlm["lastStateTs"] )
                    mlm["lastState"] = jlm["state"] # Change state
                    mlm["lastStateTs"] = jlm["ts"] # Time entering this state
                    mlm["job_state"].labels(name=jlm["name"] ).info( { "state": jlm["state"] } ) # Current state

            else: # Create Metrics
                jobList[metricNameKey] = { "metrics": {
                    "total_state_counter": pclient.Counter( "job_total_state_counter", "help", ["name", "state"]),
                    "stateTimeSec":        pclient.Counter( "job_state_time_total", "help", ["name", "state"] ),
                    "timeInState":         pclient.Gauge( "job_time_in_state".format("") , "help", ["name", "state"] ),
                    "job_state":           pclient.Info("job_state", "state",  ["name"]),
                    "lastState": jlm["state"],
                    "lastStateTs": jlm["ts"] }
                }
        print( ts, lm, metricNameBase )
        metric2.inc()

# Flask Application
app = Flask(__name__)

@app.route('/metrics', methods=['GET'])
def metrics():
    #return "<p>{}</p>".format( json.dumps(json.loads( jobList ), indent=2) ) 
    #return "<p>{}</p>".format( jobList )
    return "<p>{}</p>".format( pprint.pformat( jobList, indent=2 ))

@app.route('/loki/api/v1/push', methods=['GET', 'POST'])
def push():
    content_type = request.headers.get('Content-Type')
    if request.method == 'POST' and content_type == 'application/json':
        rj = request.json
        print("json: {}".format(rj))
        handleLogStream( rj["streams"] )
        lokiWriteStreams( rj )
        #print( request.data )
        return "<p>post</p>"
    else:
        return "<p>get</p>"
    
@app.route("/status")
def status():
    return "<p>ok</p>"

# Prometheus Client
pclient.start_http_server(prometheusHttpPort)

if __name__ == '__main__':
    # Prometheus Client
    # pclient.start_http_server(prometheusHttpPort)
    # app.run(host="localhost", port=9002, debug=True)
    # print("e")
    pass

# flask --app log-stream-processor run