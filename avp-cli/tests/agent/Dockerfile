# An agent in a shell script: avp needs only an ENTRYPOINT that answers the
# agent command line.
FROM docker.io/library/alpine:3.20
COPY agent.sh /agent.sh
ENTRYPOINT ["/agent.sh"]
