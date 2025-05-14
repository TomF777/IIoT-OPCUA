FROM python:3.12.9-slim

#Set env variable
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8

#Create non-root user
RUN addgroup localusers
RUN adduser --no-create-home localuser 
RUN usermod -g localusers localuser

ARG date

#Create catalog for the app and copy file there
RUN mkdir -p /src
WORKDIR /src
COPY /src /src

#Upgrade python and install modules
RUN pip install --upgrade pip &&\
    pip3 install -r requirements.txt

#Delete requirements after finished instalation
RUN rm requirements.txt

#Add privilage to app to non-root user
RUN chown -R localuser /src
USER localuser

#Run script
ENTRYPOINT ["python", "/src/script.py"]



