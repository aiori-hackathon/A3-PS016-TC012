// Generated model export. C++17. Scores are exploratory.
#pragma once
#include <array>
#include <cmath>
#include <cstddef>

namespace aiori_prototypes {
struct Node { int feature; float value; int left; int right; };
struct Result { bool valid; double score; int action; };
using Input = std::array<double, 7>;
inline constexpr double threshold = 0.6;
inline constexpr double missingSlope = 3.628587;
inline constexpr double intercept = 2.8619731755696405;
inline constexpr Input coefficients = {-0.16215308454232513, 0.16163314556505276, 0.16187615658798787, 0.1705363174023953, 0.0, 0.17016430203644117, 2.6611099737772687e-19};
inline constexpr Input means = {-74.2958485, -73.143214, 1.1526345, 3.6313724999999994, 1.0, 20.833332999999993, 0.10000000000000002};
inline constexpr Input scales = {0.30755695477138495, 0.35124734483765363, 0.6588031514581955, 2.176202174219631, 1.0, 12.500000000000002, 1.0};
inline constexpr int offsets[] = {0, 1, 2, 3, 4, 5, 6, 9, 12, 15, 18, 21, 24, 27, 28, 31, 34, 37, 40, 43, 46, 49, 52, 55};
inline constexpr Node nodes[] = {
    {-1, 0.174999997f, -1, -1},
    {-1, 0.158146843f, 0, 0},
    {-1, 0.143950775f, 1, 1},
    {-1, 0.131786987f, 2, 2},
    {-1, 0.121213078f, 3, 3},
    {-1, 0.111910261f, 4, 4},
    {0, -73.9583282f, 7, 8},
    {-1, 0.110748373f, 5, 5},
    {-1, 0.00844517816f, 5, 5},
    {0, -73.9583282f, 10, 11},
    {-1, 0.104205504f, 8, 8},
    {-1, 0.00815679785f, 8, 8},
    {0, -73.9583282f, 13, 14},
    {-1, 0.0982971042f, 11, 11},
    {-1, 0.00787890982f, 11, 11},
    {0, -73.9583282f, 16, 17},
    {-1, 0.0929331258f, 14, 14},
    {-1, 0.00761110475f, 14, 14},
    {0, -73.9583282f, 19, 20},
    {-1, 0.0880410895f, 17, 17},
    {-1, 0.00735295285f, 17, 17},
    {0, -73.9583282f, 22, 23},
    {-1, 0.0835620314f, 20, 20},
    {-1, 0.00710410764f, 20, 20},
    {0, -73.9583282f, 25, 26},
    {-1, 0.0794471279f, 23, 23},
    {-1, 0.00686415518f, 23, 23},
    {-1, 0.0710722432f, 26, 26},
    {0, -73.9583282f, 29, 30},
    {-1, 0.0723619908f, 27, 27},
    {-1, 0.00426463643f, 27, 27},
    {0, -73.9583282f, 32, 33},
    {-1, 0.0691030771f, 30, 30},
    {-1, 0.00412414828f, 30, 30},
    {0, -73.9583282f, 35, 36},
    {-1, 0.0660792068f, 33, 33},
    {-1, 0.00398846297f, 33, 33},
    {0, -73.9583282f, 38, 39},
    {-1, 0.0632679686f, 36, 36},
    {-1, 0.00385740143f, 36, 36},
    {0, -73.9583282f, 41, 42},
    {-1, 0.0606496744f, 39, 39},
    {-1, 0.00373081281f, 39, 39},
    {0, -73.9583282f, 44, 45},
    {-1, 0.0582069047f, 42, 42},
    {-1, 0.00360850664f, 42, 42},
    {0, -73.9583282f, 47, 48},
    {-1, 0.0559242368f, 45, 45},
    {-1, 0.00349036162f, 45, 45},
    {0, -73.9583282f, 50, 51},
    {-1, 0.0537879728f, 48, 48},
    {-1, 0.00337620568f, 48, 48},
    {0, -73.9583282f, 53, 54},
    {-1, 0.0517858267f, 51, 51},
    {-1, 0.00326590682f, 51, 51},
    {0, -73.9583282f, 56, 57},
    {-1, 0.0499068201f, 54, 54},
    {-1, 0.00315932161f, 54, 54}
};

inline std::array<Result, 2> Predict(Input x) {
    const Result invalid{false, 0.0, -1};
    if (x[4] == 0.0) x[3] = missingSlope;
    for (double value : x) {
        if (!std::isfinite(static_cast<float>(value))) return {invalid, invalid};
    }
    if ((x[4] != 0 && x[4] != 1) || std::abs(x[1] - x[0] - x[2]) > 1e-5 ||
        x[5] <= 0 || x[6] < 0 || x[6] > 0.5) return {invalid, invalid};

    float treeMargin = 0;
    for (int index : offsets) {
        while (nodes[index].feature >= 0) {
            const auto &node = nodes[index];
            index = static_cast<float>(x[node.feature]) < node.value ? node.left : node.right;
        }
        treeMargin += nodes[index].value;
    }

    double linearMargin = intercept;
    for (std::size_t i = 0; i < x.size(); ++i) {
        linearMargin += coefficients[i] * ((x[i] - means[i]) / scales[i]);
    }
    auto result = [](double margin) {
        const double score = 1.0 / (1.0 + std::exp(-margin));
        return Result{true, score, static_cast<int>(score >= threshold)};
    };
    return {result(treeMargin), result(linearMargin)};
}
} // namespace aiori_prototypes
