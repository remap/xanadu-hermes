import requests, json, io, pandas as pd
from pprint import pprint

print('json ----')
sheet_id = "1EIe9OFpqO1Wc0sYjNSKXhSRBO7k17v9wZE34b3F3TJ4"
gid = "866270832"
url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:json&gid={gid}"
r = requests.get(url)
data = json.loads(r.text[r.text.find("(")+1:r.text.rfind(")")])
pprint(data)

print('csv ----')
url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
s = requests.get(url).content
df = pd.read_csv(io.StringIO(s.decode('utf-8')))
print(df)
for _, row in df.iterrows():
    print(row['Module'], row['Group'], row['Field'], row['Value'])
