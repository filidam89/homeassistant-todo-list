ARG BUILD_FROM
FROM $BUILD_FROM

ENV LANG C.UTF-8

COPY run.sh /
COPY todo_list.py /

RUN chmod a+x /run.sh

CMD [ "/run.sh" ]