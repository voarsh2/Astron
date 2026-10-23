#include "util/Datagram.h"
#include "util/DatagramIterator.h"
#include "dclass/dc/Field.h"
#include "dclass/dc/File.h"
#include "dclass/dc/NumericType.h"
#include "dclass/dc/Struct.h"
#include "dclass/value/parse.h"
#include "dclass/value/format.h"

#include <cstdint>
#include <cstring>
#include <iostream>
#include <limits>
#include <memory>
#include <string>
#include <utility>
#include <vector>

namespace {

bool require(bool condition, const char *message)
{
    if(!condition) {
        std::cerr << message << std::endl;
    }
    return condition;
}

DatagramPtr make_sized_datagram(dgsize_t payload_length,
                               const std::vector<uint8_t> &payload)
{
    std::vector<uint8_t> bytes(sizeof(dgsize_t) + payload.size());
    dgsize_t encoded_length = swap_le(payload_length);
    std::memcpy(bytes.data(), &encoded_length, sizeof(encoded_length));
    if(!payload.empty()) {
        std::memcpy(bytes.data() + sizeof(dgsize_t), payload.data(), payload.size());
    }
    return Datagram::create(bytes);
}

bool test_iterator_bounds()
{
    auto dg = make_sized_datagram(1, {});
    DatagramIterator iterator(dg);
    try {
        iterator.read_datagram();
    } catch(const DatagramIteratorEOF &) {
        return true;
    }
    return require(false, "read_datagram accepted a payload longer than the input");
}

bool test_iterator_advance()
{
    auto dg = make_sized_datagram(2, {0x41, 0x42, 0x7f});
    DatagramIterator iterator(dg);
    auto embedded = iterator.read_datagram();
    if(!require(embedded->size() == 2, "read_datagram returned the wrong payload size")) {
        return false;
    }
    if(!require(embedded->get_data()[0] == 0x41 && embedded->get_data()[1] == 0x42,
                "read_datagram returned the wrong payload")) {
        return false;
    }
    if(!require(iterator.read_uint8() == 0x7f,
                "read_datagram did not advance past its payload")) {
        return false;
    }
    return require(iterator.get_remaining() == 0,
                   "read_datagram left an unexpected remainder");
}

bool test_unaligned_values()
{
    auto dg = Datagram::create();
    dg->add_uint8(0xa5);
    dg->add_uint32(0x12345678);
    dg->add_uint16(0x9abc);

    DatagramIterator iterator(dg);
    if(!require(iterator.read_uint8() == 0xa5, "unaligned value prefix changed")) {
        return false;
    }
    if(!require(iterator.read_uint32() == 0x12345678,
                "unaligned 32-bit value did not round-trip")) {
        return false;
    }
    return require(iterator.read_uint16() == 0x9abc,
                   "unaligned 16-bit value did not round-trip");
}

bool test_string_size()
{
    // A 32-bit size tag would require allocating more than 4 GiB to reproduce
    // the narrowing bug. The integration CI uses 16-bit tags for this case.
    if(static_cast<size_t>(DGSIZE_MAX) > 1024 * 1024) {
        return true;
    }

    auto dg = Datagram::create();
    const size_t overhead_overflow = static_cast<size_t>(DGSIZE_MAX) - sizeof(dgsize_t) + 1;
    bool rejected_tag_overhead = false;
    try {
        dg->add_string(std::string(overhead_overflow, 'x'));
    } catch(const DatagramOverflow &) {
        rejected_tag_overhead = true;
    }
    if(!require(rejected_tag_overhead,
                "add_string accepted payload plus length tag beyond datagram limit") ||
       !require(dg->size() == 0,
                "failed add_string modified the datagram before rejecting tag overhead")) {
        return false;
    }

    const std::string oversized(static_cast<size_t>(DGSIZE_MAX) + 1, 'x');
    try {
        dg->add_string(oversized);
    } catch(const DatagramOverflow &) {
        return require(dg->size() == 0,
                       "failed add_string modified the datagram before rejecting its size");
    }
    return require(false, "add_string accepted a payload larger than its size tag");
}

bool test_blob_size()
{
    if(static_cast<size_t>(DGSIZE_MAX) > 1024 * 1024) {
        return true;
    }

    auto dg = Datagram::create();
    const size_t overhead_overflow = static_cast<size_t>(DGSIZE_MAX) - sizeof(dgsize_t) + 1;
    bool rejected_tag_overhead = false;
    try {
        dg->add_blob(std::vector<uint8_t>(overhead_overflow, 0x5a));
    } catch(const DatagramOverflow &) {
        rejected_tag_overhead = true;
    }
    if(!require(rejected_tag_overhead,
                "add_blob accepted payload plus length tag beyond datagram limit") ||
       !require(dg->size() == 0,
                "failed add_blob modified the datagram before rejecting tag overhead")) {
        return false;
    }

    const std::vector<uint8_t> oversized(static_cast<size_t>(DGSIZE_MAX) + 1, 0x5a);
    try {
        dg->add_blob(oversized);
    } catch(const DatagramOverflow &) {
        return require(dg->size() == 0,
                       "failed add_blob modified the datagram before rejecting its size");
    }
    return require(false, "add_blob accepted a payload larger than its size tag");
}

bool test_raw_data_string_size()
{
    if(static_cast<size_t>(DGSIZE_MAX) > 1024 * 1024) {
        return true;
    }

    auto dg = Datagram::create();
    const std::string oversized(static_cast<size_t>(DGSIZE_MAX) + 1, 'x');
    try {
        dg->add_data(oversized);
    } catch(const DatagramOverflow &) {
        return require(dg->size() == 0,
                       "failed add_data modified the datagram before rejecting its size");
    }
    return require(false, "add_data accepted a payload larger than the datagram size limit");
}

bool test_raw_data_vector_size()
{
    if(static_cast<size_t>(DGSIZE_MAX) > 1024 * 1024) {
        return true;
    }

    auto dg = Datagram::create();
    const std::vector<uint8_t> oversized(static_cast<size_t>(DGSIZE_MAX) + 1, 0x5a);
    try {
        dg->add_data(oversized);
    } catch(const DatagramOverflow &) {
        return require(dg->size() == 0,
                       "failed add_data modified the datagram before rejecting its size");
    }
    return require(false, "add_data accepted a payload larger than the datagram size limit");
}

bool test_empty_vectors()
{
    const std::vector<uint8_t> empty;
    auto copied = Datagram::create(empty);
    if(!require(copied->size() == 0, "empty vector constructor produced data")) {
        return false;
    }

    auto dg = Datagram::create();
    dg->add_blob(empty);
    DatagramIterator iterator(dg);
    if(!require(iterator.read_blob().empty(), "empty blob did not round-trip")) {
        return false;
    }
    return require(iterator.get_remaining() == 0, "empty blob left an unexpected remainder");
}

bool test_formatter_unaligned_values()
{
    dclass::File file;
    auto structure = std::unique_ptr<dclass::Struct>(
        new dclass::Struct(&file, "UnalignedValues"));
    auto* uint8_field = new dclass::Field(new dclass::NumericType(dclass::T_UINT8));
    auto* uint32_field = new dclass::Field(new dclass::NumericType(dclass::T_UINT32));
    if(!require(structure->add_field(uint8_field),
                "could not add formatter prefix field")) {
        delete uint8_field;
        delete uint32_field;
        return false;
    }
    if(!require(structure->add_field(uint32_field),
                "could not add formatter unaligned field")) {
        delete uint32_field;
        return false;
    }
    if(!require(file.add_struct(structure.get()), "could not register formatter test struct")) {
        return false;
    }
    const dclass::Struct* formatter_type = structure.release();
    const std::vector<uint8_t> packed = {1, 0x78, 0x56, 0x34, 0x12};
    return require(dclass::format_value(formatter_type, packed) == "{1, 305419896}",
                   "formatter did not decode values after an unaligned byte field");
}

bool test_empty_formatter_input()
{
    dclass::File file;
    auto structure = std::unique_ptr<dclass::Struct>(
        new dclass::Struct(&file, "Empty"));
    if(!require(file.add_struct(structure.get()), "could not register empty test struct")) {
        return false;
    }
    const dclass::Struct* formatter_type = structure.release();
    const std::vector<uint8_t> empty_vector;
    const std::string empty_string;
    return require(dclass::format_value(formatter_type, empty_vector) == "{}" &&
                   dclass::format_value(formatter_type, empty_string) == "{}",
                   "formatter failed to handle empty vector/string input");
}

bool test_signed_integer_parser_boundaries()
{
    dclass::NumericType numeric(dclass::T_INT64);
    const std::pair<std::string, int64_t> valid_values[] = {
        {"-9223372036854775808", std::numeric_limits<int64_t>::min()},
        {"9223372036854775807", std::numeric_limits<int64_t>::max()},
    };
    for(const auto& item : valid_values) {
        bool error = false;
        const std::string packed = dclass::parse_value(&numeric, item.first, error);
        int64_t parsed = 0;
        if(!require(!error && packed.size() == sizeof(parsed),
                    "parser rejected a signed 64-bit boundary value")) {
            return false;
        }
        std::memcpy(&parsed, packed.data(), sizeof(parsed));
        if(!require(parsed == item.second,
                    "parser changed a signed 64-bit boundary value")) {
            return false;
        }
    }

    for(const char* invalid : {"9223372036854775808", "-9223372036854775809"}) {
        bool error = false;
        dclass::parse_value(&numeric, invalid, error);
        if(!require(error, "parser accepted a signed integer outside int64 range")) {
            return false;
        }
    }
    return true;
}

} // namespace

int main(int argc, char **argv)
{
    (void)argv;
    if(argc != 1) {
        std::cerr << "This executable runs the complete datagram safety test set" << std::endl;
        return 2;
    }

    struct TestCase {
        const char* name;
        bool (*run)();
    };
    const TestCase tests[] = {
        {"iterator bounds", test_iterator_bounds},
        {"iterator cursor advance", test_iterator_advance},
        {"unaligned datagram values", test_unaligned_values},
        {"string size limits", test_string_size},
        {"blob size limits", test_blob_size},
        {"raw string data size", test_raw_data_string_size},
        {"raw vector data size", test_raw_data_vector_size},
        {"empty vectors", test_empty_vectors},
        {"unaligned formatter values", test_formatter_unaligned_values},
        {"empty formatter input", test_empty_formatter_input},
        {"signed integer parser boundaries", test_signed_integer_parser_boundaries},
    };

    bool passed = true;
    for(const TestCase& test : tests) {
        if(!test.run()) {
            std::cerr << "Failed datagram safety test: " << test.name << std::endl;
            passed = false;
        }
    }
    return passed ? 0 : 1;
}
