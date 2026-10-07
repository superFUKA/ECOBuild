#pragma once

// Mark what the library exports with {{api}} (e.g. {{api}} int add(int a, int b);).
// Built as a shared library (DLL), Windows exports only the marked functions and classes.
#if defined(_WIN32) && defined({{exports}})
#define {{api}} __declspec(dllexport)
#elif defined(_WIN32) && defined({{shared}})
#define {{api}} __declspec(dllimport)
#else
#define {{api}}
#endif
