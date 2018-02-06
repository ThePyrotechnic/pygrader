//
// Created by Michael Moschetti on 9/5/17.
//
#include <iostream>
using namespace std;

int main() {

    float f1 = 0.0;
    float f2 = 0.0;
    double dub1 = 0.0;
    double dub2 = 0.0;

    for (int i = 1; i < 101; i++) {
        f1 += 1.0 / i;
        dub1 += 1.0 / i;
    }

    for (int i = 100; i > 0; i--) {
        f2 += 1.0 / i;
        dub2 += 1.0 / i;
    }

    cout << "Float forward: " << f1 << ", Float backward: " << f2 << endl;
    cout << "Double forward: " << dub1 << ", Double backward: " << dub2 << endl;
    cout << "Float difference: " << f1 - f2 << endl;
    cout << "Double difference: " << dub1 - dub2 << endl;

    return 0;
}
