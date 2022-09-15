<?php
// TODO uncomment time logging if wanted

abstract class StorageDriver {
    abstract public function get($name);
    abstract public function store($name, $data);
} 

class MemcachedStorage extends StorageDriver {
    private $memcached_;

    public function __construct($host, $port) {
        $this->memcached_ = new Memcached();
	$this->memcached_->addServer($host, $port);
	$this->memcached_->setOption(Memcached::OPT_COMPRESSION,false);
    }    

    public function get($name) {
        return $this->memcached_->get($name);
    }

    public function store($name, $data) {
        return $this->memcached_->set($name, $data);
    }
}

class MariaDbStorage extends StorageDriver {
    private $conn_;

    public function __construct($socket, $user, $pwd, $database) {
        //$this->conn_ = new mysqli(NULL, $user, $pwd, $database, NULL, $socket);
        // persistant connection
        $this->conn_ = new mysqli("p:localhost", $user, $pwd, $database, NULL, $socket);
    }    

    public function get($name) {
        $stmt = $this->conn_->prepare("SELECT data FROM test.users WHERE user=?;");
        $stmt->bind_param("s", $name);
        $stmt->execute();
        $result = $stmt->get_result();
        return $result->fetch_assoc()["data"];
    }

    public function store($name, $data) {
        $stmt = $this->conn_->prepare("INSERT INTO test.users (user, password, data) VALUES (?, \"\", ?);");
        $stmt->bind_param("ss", $name, $data);
        return $stmt->execute();    
    }
}

class FileStorage extends StorageDriver {
    const STORAGE_PATH="./store/";

    public function __construct() {
    }    

    public function get($name) {
        $data = file_get_contents(self::STORAGE_PATH . $name);
        return $data;
    }

    public function store($name, $data) {
        $file = fopen(self::STORAGE_PATH . $name, "w");
        $ret = fwrite($file, $data);
        fclose($file);

        return $ret;
    }
}


//$driver = new MemcachedStorage("/var/run/memcached/memcached.sock", 0);
$driver = new MemcachedStorage("/tmp/memcached.sock",0);

if($_SERVER["REQUEST_METHOD"] === "PUT") {
    // get filename, fail if none provided
    if(!isset($_GET["name"])) {
        http_response_code(400);
        exit(0);
    }

    // read put data 
    $data = file_get_contents("php://input");
    if(!$data) {
        http_response_code(500);
        exit(0);
    }

    // store data + get needed time
    //$start = hrtime(true);
    $result = $driver->store($_GET["name"], $data);
    //$end = hrtime(true);
    if(!$result) {
        http_response_code(500);
        exit(0);
    }

    // close write session + request (return response) before writing measurement results
    /*session_write_close(); 
    ignore_user_abort(true);
    fastcgi_finish_request();*/

    // log needed time
    /*if(array_key_exists("HTTP_X_SAMPLE", $_SERVER)) {
        $file = fopen("./meas.csv", "a");
        // get header value 
        $type = $_SERVER["HTTP_X_SAMPLE"];
        if($type == "no-cow") 
            fwrite($file, strval($end - $start) . ";" . "\n");
        else if($type == "cow")
            fwrite($file, ";" . strval($end - $start) . "\n");
        fclose($file);
    }*/
}
else if($_SERVER["REQUEST_METHOD"] === "GET") {
    if(!isset($_GET["name"])){
        http_response_code(400);
        exit(0);
    }
    
    $data = $driver->get($_GET["name"]);
    if(!$data) {
        http_response_code(404);
        exit(0);
    }

    header('Content-Type: */*');
    echo($data);
}
else {
    http_response_code(500); 
}
?>
