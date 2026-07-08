//
// Created by zhengyanzhu on 2022/11/9.
//

#include <vector>
#include <condition_variable>
#include "../Cap/CapabilityCanUse.h"
#include "../Cap/CapabilityAllocated.h"
#include "../Cap/Capability.h"
#include "../Cap/CapabilityNeed.h"
#include "../env/Environment.h"


using namespace std;

vector<Capability* >resourceCapTB;
vector<CapabilityCanUse> resourceCapCanUseTB;
CapabilityAllocated* resourceCapAllocatedTB;
CapabilityNeed* capNeedTB;
Environment* curEnv;
int UAVid = -1;
string obs0 = "111101";

int weathernums = 1;
int listening_port = 0;

volatile bool capNeedBuild;

std::condition_variable cond;
mutex my_mutex;
volatile bool envReady;

std::condition_variable cond2;
mutex my_mutex2;
volatile bool resourceCapTBReady;
volatile bool startAssess;
volatile bool startSelect;