FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64

RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-17-jre-headless \
    mysql-client \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

COPY starrocks-fe_*.deb starrocks-be_*.deb /tmp/
RUN dpkg -i /tmp/starrocks-fe_*.deb /tmp/starrocks-be_*.deb && rm /tmp/*.deb

# Replace BE's stub libjvm.so with symlink to real JDK libjvm.so.
# The deb ships an 8.5KB placeholder that returns -1 from JNI_GetCreatedJavaVMs;
# the real JDK libjvm.so (24MB) must be used for JDBC/JNI to work.
RUN rm -f /usr/lib/starrocks/be/lib/libjvm.so && \
    ln -s /usr/lib/jvm/java-17-openjdk-amd64/lib/server/libjvm.so /usr/lib/starrocks/be/lib/libjvm.so

RUN echo "arrow_flight_port = 9408" >> /etc/starrocks/fe/fe.conf && \
    echo "default_replication_num = 1" >> /etc/starrocks/fe/fe.conf && \
    echo "black_host_history_sec = 1" >> /etc/starrocks/fe/fe.conf && \
    echo "black_host_penalty_min_ms = 1" >> /etc/starrocks/fe/fe.conf && \
    echo "black_host_connect_failures_within_time = 2147483647" >> /etc/starrocks/fe/fe.conf && \
    echo "arrow_flight_port = 9419" >> /etc/starrocks/be/be.conf

COPY drivers/ /opt/starrocks/drivers/
COPY data/ /opt/starrocks/data/

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 9030 8030 9408 9050 9419
ENTRYPOINT ["/entrypoint.sh"]
