#ifndef IROS_UBISCHED_BRIDGE_CLIENT_H
#define IROS_UBISCHED_BRIDGE_CLIENT_H

// Optional, bounded, fail-safe client for the legacy iS2ROS observation protocol.
// Wire request:  UBI1|<uav_id>|<digit_observation>
// Wire response: OK|<task_index>|<sensor_index>  or NONE or ERR|...
// This is not a task-execution acknowledgement channel.

#include <arpa/inet.h>
#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <string>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>

class UbiSchedBridgeClient {
public:
    enum Result { DISABLED, ASSIGNED, NO_ASSIGNMENT, FAILED };

    static bool enabled() {
        const char* v = std::getenv("UBISCHED_BRIDGE_ENABLE");
        return v != NULL && std::strcmp(v, "1") == 0;
    }

    static Result request(int uavId, const std::string& obs, int& taskId, int& sensorId) {
        if (!enabled()) return DISABLED;
        if (uavId < 1 || uavId > 9999 || obs.size() < 2 || obs.size() > 49) return FAILED;
        for (size_t i = 0; i < obs.size(); ++i) {
            if (obs[i] < '0' || obs[i] > '9') return FAILED;
        }
        const char* ip = std::getenv("UBISCHED_BRIDGE_HOST");
        if (ip == NULL || !*ip) ip = "127.0.0.1";
        const char* portText = std::getenv("UBISCHED_BRIDGE_PORT");
        char* tail = NULL;
        long port = portText ? std::strtol(portText, &tail, 10) : 18765;
        if (port < 1 || port > 65535 || (portText && (!*portText || *tail))) return FAILED;
        int fd = socket(AF_INET, SOCK_DGRAM, 0);
        if (fd < 0) return FAILED;
        struct sockaddr_in addr;
        std::memset(&addr, 0, sizeof(addr));
        addr.sin_family = AF_INET;
        addr.sin_port = htons(static_cast<unsigned short>(port));
        if (inet_pton(AF_INET, ip, &addr.sin_addr) != 1 ||
            connect(fd, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) < 0) {
            close(fd);
            return FAILED;
        }
        struct timeval timeout;
        timeout.tv_sec = 0;
        timeout.tv_usec = 350000;
        setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
        std::string packet = "UBI1|" + std::to_string(uavId) + "|" + obs;
        if (send(fd, packet.c_str(), packet.size(), 0) != static_cast<ssize_t>(packet.size())) {
            close(fd);
            return FAILED;
        }
        char buffer[128];
        ssize_t received = recv(fd, buffer, sizeof(buffer) - 1, 0);
        close(fd);
        if (received <= 0) return FAILED;
        buffer[received] = '\0';
        std::string response(buffer, static_cast<size_t>(received));
        if (response == "NONE") return NO_ASSIGNMENT;
        if (response.compare(0, 3, "OK|") != 0) return FAILED;
        // Strict full-message parse. Invalid or out-of-mask assignments never reach Dispatch.
        const size_t sep = response.find('|', 3);
        if (sep == std::string::npos || response.find('|', sep + 1) != std::string::npos) return FAILED;
        const std::string t = response.substr(3, sep - 3);
        const std::string s = response.substr(sep + 1);
        if (t.empty() || s.empty() || t.size() > 2 || s.size() > 1) return FAILED;
        for (size_t i = 0; i < t.size(); ++i) if (t[i] < '0' || t[i] > '9') return FAILED;
        for (size_t i = 0; i < s.size(); ++i) if (s[i] < '0' || s[i] > '9') return FAILED;
        const int ti = std::atoi(t.c_str());
        const int si = std::atoi(s.c_str());
        if (ti < 0 || static_cast<size_t>(ti + 1) >= obs.size() || obs[ti + 1] == '0'
            || si < 0 || si > 2) return FAILED;
        taskId = ti;
        sensorId = si;
        return ASSIGNED;
    }
};

#endif
