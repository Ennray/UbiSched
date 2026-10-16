#ifndef IROS_UBISCHED_STRUCTURED_CLIENT_H
#define IROS_UBISCHED_STRUCTURED_CLIENT_H

// Stage 13 opt-in. A separate producer must atomically write a current UBI2
// snapshot JSON to UBISCHED_STRUCTURED_STATE_FILE. This client does not infer
// a task DAG from obs0 or report any execution completion to the scheduler.
// UBI2C|UAV<id>|<json> -> OK|legacy_task|legacy_sensor / NONE / ERR|...

#include "UbiSchedBridgeClient.h"
#include <arpa/inet.h>
#include <cstdlib>
#include <fstream>
#include <iterator>
#include <string>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>

class UbiSchedStructuredClient {
public:
    static UbiSchedBridgeClient::Result request(int uavId, const std::string& obs,
                                                 const std::string& file,
                                                 int& taskId, int& sensorId) {
        using Client = UbiSchedBridgeClient;
        if (uavId < 1 || uavId > 9999 || file.empty() || obs.size() < 2 || obs.size() > 49)
            return Client::FAILED;
        for (size_t i=0; i<obs.size(); ++i)
            if (obs[i] < '0' || obs[i] > '9') return Client::FAILED;
        std::ifstream in(file.c_str(), std::ios::binary);
        if (!in.good()) return Client::FAILED;
        std::string json((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
        if (json.empty() || json.size() > 45000 || json[0] != '{') return Client::FAILED;
        const char* host = std::getenv("UBISCHED_STRUCTURED_HOST");
        if (!host || !*host) host = "127.0.0.1";
        const char* portText = std::getenv("UBISCHED_STRUCTURED_PORT");
        char* tail = NULL;
        long port = portText ? std::strtol(portText, &tail, 10) : 18766;
        if (port < 1 || port > 65535 || (portText && (!*portText || *tail)))
            return Client::FAILED;
        int fd = socket(AF_INET, SOCK_DGRAM, 0);
        if (fd < 0) return Client::FAILED;
        struct sockaddr_in addr = {};
        addr.sin_family = AF_INET;
        addr.sin_port = htons(static_cast<unsigned short>(port));
        if (inet_pton(AF_INET, host, &addr.sin_addr) != 1 ||
            connect(fd, reinterpret_cast<struct sockaddr*>(&addr), sizeof(addr)) < 0) {
            close(fd); return Client::FAILED;
        }
        struct timeval timeout = {};
        timeout.tv_sec = 2; // Cold model loading requires more than legacy 350ms.
        if (setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) < 0) {
            close(fd); return Client::FAILED;
        }
        std::string packet = "UBI2C|UAV" + std::to_string(uavId) + "|" + json;
        if (send(fd, packet.data(), packet.size(), 0) != static_cast<ssize_t>(packet.size())) {
            close(fd); return Client::FAILED;
        }
        char buf[160];
        ssize_t n = recv(fd, buf, sizeof(buf)-1, 0);
        close(fd);
        if (n <= 0) return Client::FAILED;
        buf[n] = '\0';
        std::string reply(buf, static_cast<size_t>(n));
        if (reply == "NONE") return Client::NO_ASSIGNMENT;
        if (reply.compare(0,3,"OK|") != 0) return Client::FAILED;
        size_t sep = reply.find('|',3);
        if (sep == std::string::npos || reply.find('|',sep+1) != std::string::npos)
            return Client::FAILED;
        std::string t = reply.substr(3,sep-3), s = reply.substr(sep+1);
        if (t.empty() || s.empty() || t.size()>2 || s.size()>1)
            return Client::FAILED;
        for (char c: t) if (c<'0'||c>'9') return Client::FAILED;
        for (char c: s) if (c<'0'||c>'9') return Client::FAILED;
        int ti = std::atoi(t.c_str()), si = std::atoi(s.c_str());
        if (ti<0 || static_cast<size_t>(ti+1)>=obs.size() || obs[ti+1]=='0'
            || si<0 || si>2) return Client::FAILED;
        taskId = ti; sensorId = si;
        return Client::ASSIGNED;
    }
};

#endif
