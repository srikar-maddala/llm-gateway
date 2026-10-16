import redis
r=redis.Redis(host='localhost',port=6379,decode_responses=True)

print(r.ping()) #True means connected

r.set("greeting",'hello') #store a value

print(r.get('greeting')) #read it back

r.incr('counter')  # add 1 to a number
r.incr('counter')
print(r.get('counter')) #2