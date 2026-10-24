#include <mongocxx/client.hpp>
#include <mongocxx/instance.hpp>
#include <mongocxx/uri.hpp>

#include <exception>
#include <iostream>

int main(int argc, char **argv)
{
    if(argc != 2) {
        std::cerr << "Usage: astron_mongo_test_cleanup <MongoDB URI>\n";
        return 2;
    }

    try {
        mongocxx::instance instance{};
        const mongocxx::uri uri{argv[1]};
        const auto database_name = uri.database();
        if(database_name.empty()) {
            std::cerr << "MongoDB test URI must include a database name\n";
            return 2;
        }

        mongocxx::client client{uri};
        client[database_name].drop();
    } catch(const std::exception &error) {
        std::cerr << "Failed to remove the MongoDB test database: "
                  << error.what() << '\n';
        return 1;
    }

    return 0;
}
