cmake_minimum_required(VERSION 3.16)
project(edgehome_rkllm_runtime LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(RKLLM_API_PATH "" CACHE PATH "Path containing include/rkllm.h and aarch64/librkllmrt.so")
set(NLOHMANN_JSON_INCLUDE_DIR "/usr/include" CACHE PATH "Path containing nlohmann/json.hpp")

if(NOT EXISTS "${RKLLM_API_PATH}/include/rkllm.h")
  message(FATAL_ERROR "Set RKLLM_API_PATH to rkllm-runtime/Linux/librkllm_api")
endif()
if(NOT EXISTS "${RKLLM_API_PATH}/aarch64/librkllmrt.so")
  message(FATAL_ERROR "Missing ${RKLLM_API_PATH}/aarch64/librkllmrt.so")
endif()
if(NOT EXISTS "${NLOHMANN_JSON_INCLUDE_DIR}/nlohmann/json.hpp")
  message(FATAL_ERROR "Missing ${NLOHMANN_JSON_INCLUDE_DIR}/nlohmann/json.hpp")
endif()

function(add_edgehome_launcher target source)
  add_executable(${target} ${source})
  target_include_directories(${target} PRIVATE "${RKLLM_API_PATH}/include")
  target_link_libraries(${target} PRIVATE
    "${RKLLM_API_PATH}/aarch64/librkllmrt.so"
    gomp
    pthread
  )
  target_link_options(${target} PRIVATE -static-libstdc++ -static-libgcc)
  install(TARGETS ${target} RUNTIME DESTINATION bin)
endfunction()

add_edgehome_launcher(edgehome_rkllm_persistent src/edgehome_rkllm_persistent.cpp)
target_compile_definitions(edgehome_rkllm_persistent PRIVATE EDGEHOME_RKLLM_API_1_3=1)
add_edgehome_launcher(rkllm_structured_persistent src/rkllm_structured_persistent.cpp)
# Host /usr/include contains the header-only JSON dependency.  Keep it after
# the cross compiler's AArch64 sysroot so host stdint/bits headers never win.
target_compile_options(rkllm_structured_persistent PRIVATE
  -idirafter "${NLOHMANN_JSON_INCLUDE_DIR}"
)
