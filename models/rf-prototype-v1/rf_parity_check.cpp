#include "rf_prototype.hpp"
#include <iostream>
struct Check { const char* id; std::array<double,7> x; bool valid; double p; int action; };
int main() {
    const Check checks[] = {
    {"training-state-0", {{-74.022006,-73.457015,0.564991,5.794893,1.0,33.333333,0.1}}, true, 0.9808879966460269, 1},
    {"training-state-1", {{-74.565653,-72.83662,1.729033,5.820208,1.0,33.333333,0.1}}, true, 1.0, 1},
    {"training-state-2", {{-73.958329,-73.527555,0.430774,1.448108,1.0,8.333333,0.1}}, true, 0.4632145485970288, 0},
    {"training-state-3", {{-74.637406,-72.751666,1.88574,1.462281,1.0,8.333333,0.1}}, true, 0.9827831296992481, 1},
    {"missing-trend-fixture", {{-74.022006,-73.457015,0.564991,std::numeric_limits<double>::quiet_NaN(),0.0,33.333333,0.1}}, true, 0.9808879966460269, 1},
    {"invalid-serving-fixture", {{std::numeric_limits<double>::quiet_NaN(),-73.457015,0.564991,5.794893,1.0,33.333333,0.1}}, false, 0.0, -1}
    };
    for (const auto& c : checks) {
        auto prediction = aiori_rf_prototype::Predict(c.x);
        if (prediction.valid != c.valid || prediction.action != c.action ||
            (c.valid && std::abs(prediction.probability_handover-c.p) > 1e-12)) {
            std::cerr << "FAIL " << c.id << "\n"; return 1;
        }
    }
    std::cout << "PASS: C++ inference matches golden predictions\n";
    return 0;
}
